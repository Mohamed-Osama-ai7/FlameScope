"""Fetch a PSI investigation's experimental table with provenance (read-only on NASA's side).

Usage (from repository root):
    python backend/scripts/fetch_psi_table.py PSI-69 PSI-25 PSI-98

For each id: reads investigation metadata, downloads each ``experimentalTable`` file, checks the
byte size against PSI's recorded ``file_size``, stores it immutably under
``data/raw/<id>/experimental_table/`` and appends a row to ``data/metadata/artifact_manifest.csv``.
An existing raw file with different bytes is never overwritten. Network calls use finite timeouts
and bounded retries.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

API = "https://psi.nasa.gov/geode-py/ws"
ALLOWED_HOST_SUFFIXES = ("psi.nasa.gov", ".amazonaws.com")
USER_AGENT = "flamescope-provenance-fetcher/0.1"
MANIFEST_FIELDS = [
    "source_id",
    "artifact_kind",
    "file_name",
    "relative_path",
    "byte_size",
    "expected_byte_size",
    "sha256",
    "source_url",
    "psi_file_version",
    "psi_s3_version_id",
    "license",
    "retrieved_at_utc",
]


@dataclass(frozen=True)
class ManifestRow:
    source_id: str
    artifact_kind: str
    file_name: str
    relative_path: str
    byte_size: int
    expected_byte_size: int
    sha256: str
    source_url: str
    psi_file_version: str
    psi_s3_version_id: str
    license: str
    retrieved_at_utc: str


class FetchError(RuntimeError):
    pass


def host_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        host == s.lstrip(".") or host.endswith(s) for s in ALLOWED_HOST_SUFFIXES
    )


def download_url(source_id: str, file_name: str, version: int) -> str:
    query = urllib.parse.urlencode({"file": file_name, "version": version, "redirect": "false"})
    return f"{API}/studies/{source_id}/download?{query}"


def resolve_payload(body: bytes, content_type: str) -> tuple[str | None, bytes | None]:
    """Return (indirect_url, None) for a pointer response, or (None, body) for file bytes.

    PSI's ``redirect=false`` endpoint answers with a bare presigned S3 URL as text/html.
    """
    text = body.strip()
    if len(text) < 8192 and text.startswith(b"https://") and not any(c in text for c in b"\r\n ,"):
        return text.decode("ascii"), None
    if "json" in content_type.lower():
        data = json.loads(body)
        candidates = [data] if isinstance(data, str) else [
            data.get(k) for k in ("url", "signed_url", "download_url", "location")
        ] if isinstance(data, dict) else []
        for c in candidates:
            if isinstance(c, str) and c.startswith("https://"):
                return c, None
        raise FetchError(f"JSON response without a usable URL: {str(data)[:200]}")
    return None, body


def check_size(actual: int, expected: int, file_name: str) -> None:
    if expected and actual != expected:
        raise FetchError(f"{file_name}: got {actual} bytes, PSI metadata says {expected}")


def store_immutable(target: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    if target.exists():
        existing = hashlib.sha256(target.read_bytes()).hexdigest()
        if existing != digest:
            raise FetchError(f"{target} exists with different bytes; raw files are immutable")
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return digest


def append_manifest(manifest: Path, row: ManifestRow) -> None:
    rows: list[dict[str, str]] = []
    if manifest.exists():
        with manifest.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    key = (row.relative_path, row.sha256)
    if any((r["relative_path"], r["sha256"]) == key for r in rows):
        return
    rows.append({k: str(v) for k, v in asdict(row).items()})
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _get(url: str, timeout: float, attempts: int) -> tuple[bytes, str]:
    if not host_allowed(url):
        raise FetchError(f"refusing to fetch from non-allowed host: {url}")
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (host checked)
                return resp.read(), resp.headers.get("Content-Type", "")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(5 * (i + 1))
    raise FetchError(f"{url}: failed after {attempts} attempts: {last}")


def fetch(source_id: str, root: Path, timeout: float, attempts: int) -> list[ManifestRow]:
    meta_body, _ = _get(f"{API}/repo/investigations/{source_id}", timeout, attempts)
    meta = json.loads(meta_body)
    license_id = meta.get("licenseIdentifier") or ""
    rows: list[ManifestRow] = []
    for entry in meta.get("experimentalTable", []):
        if entry.get("restricted"):
            raise FetchError(f"{source_id}: {entry.get('file_name')} is marked restricted")
        name, version = entry["file_name"], int(entry.get("version") or 1)
        public_url = download_url(source_id, name, version)
        body, ctype = _get(public_url, timeout, attempts)
        indirect, data = resolve_payload(body, ctype)
        if indirect is not None:
            data, _ = _get(indirect, timeout, attempts)
        assert data is not None
        expected = int(entry.get("file_size") or 0)
        check_size(len(data), expected, name)
        rel = Path("data") / "raw" / source_id / "experimental_table" / name
        digest = store_immutable(root / rel, data)
        rows.append(
            ManifestRow(
                source_id=source_id,
                artifact_kind="psi_experimental_table",
                file_name=name,
                relative_path=rel.as_posix(),
                byte_size=len(data),
                expected_byte_size=expected,
                sha256=digest,
                source_url=public_url,  # stable public endpoint, never a presigned URL
                psi_file_version=str(version),
                psi_s3_version_id=str(entry.get("s3_version_id") or ""),
                license=license_id,
                retrieved_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ids", nargs="+")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args(argv)
    manifest = args.root / "data" / "metadata" / "artifact_manifest.csv"
    failed = False
    for sid in args.source_ids:
        try:
            for row in fetch(sid, args.root, args.timeout, args.attempts):
                append_manifest(manifest, row)
                print(f"OK   {sid}: {row.relative_path} {row.byte_size} B sha256={row.sha256}")
        except (FetchError, json.JSONDecodeError, KeyError) as exc:
            failed = True
            print(f"FAIL {sid}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
