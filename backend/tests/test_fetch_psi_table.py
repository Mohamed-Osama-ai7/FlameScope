"""Offline tests of the PSI fetcher's provenance logic (no network)."""
import csv
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "fetch_psi_table", Path(__file__).resolve().parents[1] / "scripts" / "fetch_psi_table.py"
)
assert _spec and _spec.loader
fp = importlib.util.module_from_spec(_spec)
sys.modules["fetch_psi_table"] = fp  # dataclasses resolve their module via sys.modules
_spec.loader.exec_module(fp)


def test_host_allowlist():
    assert fp.host_allowed("https://psi.nasa.gov/geode-py/ws/x")
    assert fp.host_allowed("https://bucket.s3.us-east-1.amazonaws.com/f.csv")
    assert not fp.host_allowed("http://psi.nasa.gov/x")
    assert not fp.host_allowed("https://psi.nasa.gov.evil.example/x")
    assert not fp.host_allowed("https://example.com/f.csv")


def test_resolve_json_pointer_and_raw_bytes():
    url, data = fp.resolve_payload(b'{"url": "https://psi.nasa.gov/f.csv"}', "application/json")
    assert url == "https://psi.nasa.gov/f.csv" and data is None
    presigned = b"https://psi-repo-prod.s3.amazonaws.com/psi-data/x.csv?versionId=v&Signature=s\n"
    url, data = fp.resolve_payload(presigned, "text/html; charset=utf-8")
    assert url and url.startswith("https://psi-repo-prod.s3.amazonaws.com/") and data is None
    url, data = fp.resolve_payload(b"a,b\n1,2\n", "text/csv")
    assert url is None and data == b"a,b\n1,2\n"
    with pytest.raises(fp.FetchError):
        fp.resolve_payload(b'{"status": "error"}', "application/json")


def test_size_mismatch_rejected():
    fp.check_size(10, 10, "f")
    with pytest.raises(fp.FetchError):
        fp.check_size(9, 10, "f")


def test_raw_files_are_immutable(tmp_path):
    target = tmp_path / "raw" / "f.csv"
    h1 = fp.store_immutable(target, b"abc")
    assert fp.store_immutable(target, b"abc") == h1  # idempotent
    with pytest.raises(fp.FetchError):
        fp.store_immutable(target, b"abd")
    assert target.read_bytes() == b"abc"


def test_manifest_is_deduplicated(tmp_path):
    row = fp.ManifestRow(
        source_id="S", artifact_kind="k", file_name="f.csv", relative_path="data/raw/S/f.csv",
        byte_size=3, expected_byte_size=3, sha256="0" * 64, source_url="https://psi.nasa.gov/x",
        psi_file_version="1", psi_s3_version_id="", license="CC0-1.0",
        retrieved_at_utc="2026-11-13T00:00:00Z",
    )
    manifest = tmp_path / "m.csv"
    fp.append_manifest(manifest, row)
    fp.append_manifest(manifest, row)
    with manifest.open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 1
