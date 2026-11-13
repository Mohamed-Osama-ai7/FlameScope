"""The Exploration Lab dataset must be a faithful, deterministic packaging of the approved v0.2.0 analysis."""
import hashlib
import json
import subprocess
import sys

import pytest

from app.api.routes import PROJECT_ROOT

DATASET = PROJECT_ROOT / "frontend" / "public" / "data" / "flex_lab_dataset_v0.2.0.json"
SUMMARY = PROJECT_ROOT / "reports" / "flex_run_level_v0.2" / "summary.json"
SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "export_lab_dataset.py"
RAW = PROJECT_ROOT / "data" / "raw" / "PSI-69" / "experimental_table" / "PSI-69_Experimental table_FLEX.csv"


@pytest.fixture(scope="module")
def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_provenance_matches_artifacts(dataset):
    prov = dataset["provenance"]
    manifest = (PROJECT_ROOT / "data" / "metadata" / "artifact_manifest.csv").read_text(encoding="utf-8")
    assert prov["raw_sha256"] in manifest
    assert prov["analysis_summary_sha256"] == hashlib.sha256(SUMMARY.read_bytes()).hexdigest()
    enrich = PROJECT_ROOT / "data" / "derived" / "flex_enrichment_v1.csv"
    assert prov["enrichment_sha256"] == hashlib.sha256(enrich.read_bytes()).hexdigest()
    assert dataset["synthetic"] is False and dataset["analysis_version"] == "0.2.0"


def test_records_and_strata_match_the_v02_analysis(dataset):
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert len(dataset["records"]) == summary["scope"]["psi_rows_analysed"] == 274
    assert len({r["record_key"] for r in dataset["records"]}) == 274
    py = summary["results"]["strata"]
    assert len(dataset["strata"]) == len(py) == 137
    for a, b in zip(dataset["strata"], py, strict=True):
        assert a["analysis"] == b["analysis"] and a["n"] == b["n"]
        assert a["rho_spearman"] == b["rho_spearman"]  # statistics are passed through, not recomputed
        assert a["psi_rows"] == b["psi_rows"]


def test_eligibility_comes_from_strata_membership(dataset):
    by_row = {r["psi_row"]: r for r in dataset["records"]}
    for s in dataset["strata"]:
        code = s["analysis"].split("_")[0]
        for n in s["psi_rows"]:
            assert code in by_row[n]["eligible"]


def test_reported_k_is_not_confused_with_calculated_k(dataset):
    assert "d2-law calculator is not used" in dataset["value_origin"]
    assert "burning_rate_constant_d2_fit_mm2_s" not in json.dumps(dataset["records"][:5])
    assert dataset["units"]["burning_rate_constant_mm2_s"] == "mm²/s"


def test_unknown_fields_are_declared_not_invented(dataset):
    assert any("H2O" in f for f in dataset["unknown_fields"])
    blob = json.dumps(dataset["records"])
    assert "h2o" not in blob.lower() or "H2O" in " ".join(dataset["unknown_fields"])


def test_export_is_deterministic():
    before = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    if not RAW.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    for _ in range(2):
        subprocess.run([sys.executable, str(SCRIPT)], check=True, capture_output=True, timeout=120)
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == before
