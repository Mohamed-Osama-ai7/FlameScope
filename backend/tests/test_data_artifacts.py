"""Consistency of acquired NASA artifacts, manifest, registry and variable dictionary."""
import csv
import hashlib

import pytest

from app.api.routes import PROJECT_ROOT, REGISTRY_PATH
from app.domain.sources import VerificationStatus, load_registry

META = PROJECT_ROOT / "data" / "metadata"


def _rows(name):
    with (META / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_manifest_matches_registry():
    registry = {r.source_id: r for r in load_registry(REGISTRY_PATH)}
    for row in _rows("artifact_manifest.csv"):
        rec = registry[row["source_id"]]
        assert rec.sha256 == row["sha256"]
        assert rec.raw_file_path == row["relative_path"]
        assert row["byte_size"] == row["expected_byte_size"]
        assert row["license"] == "CC0-1.0"
        assert "Signature" not in row["source_url"]  # never store presigned URLs


@pytest.mark.parametrize("row", _rows("artifact_manifest.csv"), ids=lambda r: r["source_id"])
def test_raw_artifact_hash_if_present(row):
    path = PROJECT_ROOT / row["relative_path"]
    if not path.exists():  # raw data is gitignored; a fresh clone must re-fetch
        pytest.skip(f"{row['relative_path']} not present locally")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_variable_dictionary_flags():
    rows = _rows("variable_dictionary.csv")
    registry = {r.source_id: r for r in load_registry(REGISTRY_PATH)}
    assert {r["source_id"] for r in rows} <= set(registry)
    by_col = {(r["source_id"], r["source_column"]): r for r in rows}
    assert by_col[("PSI-69", "Burning rate; mm")]["mapping_status"] == "RESOLVED"
    assert by_col[("PSI-69", "CO initial ambient composition; mole fraction")][
        "mapping_status"
    ] == "RESOLVED"
    assert by_col[("PSI-25", "(no column)")]["mapping_status"] == "NOT_PRESENT"
    quarantined = {s for s, r in registry.items() if r.verification_status is VerificationStatus.QUARANTINED}
    for r in rows:
        if r["source_id"] in quarantined:
            assert r["mapping_status"] == "QUARANTINED"
