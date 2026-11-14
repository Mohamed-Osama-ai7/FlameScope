"""Read-only inventory of local data files with SHA-256 hashes."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    if not root.exists():
        raise FileNotFoundError(f"Data directory does not exist: {root}")
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append(
            {
                "relative_path": path.as_posix(),
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/metadata/local_file_inventory.csv"))
    args = parser.parse_args()

    rows = inventory(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["relative_path", "file_name", "extension", "byte_size", "sha256"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Inventoried {len(rows)} files -> {args.output}")
    print("Note: hashes identify file bytes; they do not validate scientific correctness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
