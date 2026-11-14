"""Integrity gap closure (docs/22): central PSI-25 exclusion, no unregistered support modes as analysis input,
PENDING_VERIFICATION in every PSI-69 export, consumers reject INVALID/MISSING cells."""

from __future__ import annotations

import filecmp
import json
import subprocess
import sys

import pytest

from app.analysis import flex_run_level as fx
from app.analysis.export_guard import REJECT_FLAGS, usable_value
from app.domain.eligibility import EligibilityPolicy, explicit_exclusion
from app.rag.config import PROJECT_ROOT

DATASET = PROJECT_ROOT / "frontend/public/data/flex_lab_dataset_v0.2.0.json"
V03 = PROJECT_ROOT / "reports/flex_run_level_v0.3"
SHORT = {
    "X_O2": "ambient_oxygen_mole_fraction",
    "X_CO2": "co2_mole_fraction",
    "X_He": "ambient_helium_mole_fraction",
    "P_mmHg": "ambient_pressure",
    "D0_mm": "initial_droplet_diameter",
    "K_reported_mm2_s": "burning_rate_constant_mm2_s",
    "Dext_mm": "extinction_diameter",
}


def dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 1. central PSI-25 exclusion


def test_explicit_exclusion_is_read_from_the_shared_decision_file():
    assert explicit_exclusion(PROJECT_ROOT, "PSI-25") == "ACQUIRED_BUT_EXCLUDED"
    assert explicit_exclusion(PROJECT_ROOT, "PSI-98") == "QUARANTINED"
    assert explicit_exclusion(PROJECT_ROOT, "PSI-69") is None
    assert (
        explicit_exclusion(PROJECT_ROOT, "NOT-A-SOURCE") is None
    )  # unknown: default deny is the policy's job
    assert not EligibilityPolicy(PROJECT_ROOT).decision("NOT-A-SOURCE").usable_as_evidence


# ------------------------------------------------------------- 2. support modes are not an analysis input


def _runs() -> list[fx.FlexRun]:
    man = PROJECT_ROOT / "data/metadata/artifact_manifest.csv"
    entry = fx.manifest_entry(man)
    raw = PROJECT_ROOT / entry["relative_path"]
    if not raw.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    runs, _ = fx.load_verified(raw, man)
    fx.attach_enrichment(runs, PROJECT_ROOT / "data/derived/flex_enrichment_v1.csv")
    return runs


def test_v03_strata_never_use_support_mode():
    res = fx.run_analyses(_runs(), stratify_by_support_mode=False)
    assert res["strata"] and {s["stratum"].get("support_mode") for s in res["strata"]} == {fx.NOT_CONTROLLED}


def test_v03_outputs_are_committed_reproducible_and_labelled(tmp_path):
    _runs()  # skip without raw data
    s = json.loads((V03 / "summary.json").read_text(encoding="utf-8"))
    assert s["analysis_version"] == "0.3.0"
    assert s["evidence_eligibility"] == {"PSI-69": "PENDING_VERIFICATION"}
    assert s["analysis_choices"]["support_mode_stratification"].startswith("NOT used")
    assert isinstance(s["reported_K_by_fuel_and_support_mode"], str)
    script = PROJECT_ROOT / "backend/scripts/run_flex_analysis.py"
    subprocess.run(
        [sys.executable, str(script), "--no-support-mode", "--out", str(tmp_path)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    for f in ("summary.json", "strata_results.csv", "quality_report.json", "descriptive_by_fuel.csv"):
        assert filecmp.cmp(tmp_path / f, V03 / f, shallow=False), f  # byte-identical regeneration


def test_platform_labels_support_mode_provenance():
    pytest.importorskip("app.data_platform")
    from app.data_platform.extract_flex import extract
    from app.domain.sources import find_source, load_registry

    _runs()
    src = find_source(load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv"), "PSI-69")
    b = extract(PROJECT_ROOT, src, PROJECT_ROOT / "data/metadata/artifact_manifest.csv")
    assert all("UNREGISTERED" in r["derived_attributes"]["support_mode_provenance"] for r in b.runs)


# ------------------------------------------------------------------ 3. PENDING_VERIFICATION in exports


def test_lab_export_states_pending_verification_and_support_mode_status():
    ev = dataset()["evidence_status"]
    assert ev["eligibility"] == EligibilityPolicy(PROJECT_ROOT).decision("PSI-69").eligibility.value
    assert ev["eligibility"] == "PENDING_VERIFICATION" and ev["approval_status"] == "pending_verification"
    assert "UNREGISTERED" in ev["support_mode"] and "never scientific evidence" in ev["support_mode"]


# ------------------------------------------------------------------ 4. consumers reject INVALID / MISSING


def test_every_flagged_cell_is_unusable_and_the_guard_rejects_it():
    recs = dataset()["records"]
    flagged = 0
    for r in recs:
        for field, flags in r["field_flags"].items():
            if set(flags) & REJECT_FLAGS:
                flagged += 1
                assert r["usable"][field] is False, (r["record_key"], field)
                assert usable_value(r, field) is None, (r["record_key"], field)
    assert flagged >= 112  # 111 missing + 1 invalid PSI-69 cells (Data Platform / RAG counts)
    r114 = next(r for r in recs if r["psi_row"] == 114)
    assert r114["values"]["ambient_pressure"] == 0.0 and usable_value(r114, "ambient_pressure") is None
    assert usable_value(r114, "burning_rate_constant_mm2_s") == 0.42


def test_guard_trusts_flags_over_a_stale_usable_map():
    rec = {
        "values": {"ambient_pressure": 0.0},
        "usable": {"ambient_pressure": True},
        "field_flags": {"ambient_pressure": ["invalid_nonpositive_pressure"]},
    }
    assert usable_value(rec, "ambient_pressure") is None


@pytest.mark.parametrize("version", ["v0.2", "v0.3"])
def test_analysis_strata_contain_only_usable_inputs(version):
    usable = {r["psi_row"]: r["usable"] for r in dataset()["records"]}
    strata = json.loads(
        (PROJECT_ROOT / f"reports/flex_run_level_{version}/summary.json").read_text(encoding="utf-8")
    )["results"]["strata"]
    for s in strata:
        for row in s["psi_rows"]:
            assert usable[row][SHORT[s["x"]]] and usable[row][SHORT[s["y"]]], (version, s["analysis"], row)
