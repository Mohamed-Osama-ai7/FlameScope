"""Vision outputs expose the evidence status of PSI-69 and never use report-derived (unregistered) inputs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.data_platform.settings import project_root
from app.domain.eligibility import EligibilityPolicy
from app.main import app
from app.vision.eligibility import (
    evidence_eligibility,
    reference_eligibility,
    reference_source_ids,
    vision_source_ids,
)

ROOT = project_root()
OUT = ROOT / "data/derived/flame_vision"
client = TestClient(app)
PENDING = {"PSI-69": "PENDING_VERIFICATION"}
UNREGISTERED_REF = {"NASA-TP-2015-216046": "UNREGISTERED"}


def test_vision_sources_and_status_come_from_the_central_policy():
    assert vision_source_ids(ROOT) == ["PSI-69"]
    assert evidence_eligibility(ROOT) == PENDING
    # the published report is a labelled cross-check reference, reported separately and never as evidence
    assert reference_source_ids(ROOT) == ["NASA-TP-2015-216046"]
    assert reference_eligibility(ROOT) == UNREGISTERED_REF
    assert EligibilityPolicy(ROOT).decision("PSI-69").eligibility.value == "PENDING_VERIFICATION"


def test_api_results_state_pending_verification():
    ev = client.get("/api/v1/vision/evaluation")
    assert ev.status_code == 200 and ev.json()["evidence_eligibility"] == PENDING
    assert ev.json()["reference_eligibility"] == UNREGISTERED_REF
    tests = sorted(p.name for p in OUT.iterdir() if p.is_dir())
    assert tests  # committed results exist
    for t in tests:
        r = client.get(f"/api/v1/vision/tests/{t}")
        assert r.status_code == 200 and r.json()["evidence_eligibility"] == PENDING, t
        assert r.json()["reference_eligibility"] == UNREGISTERED_REF, t


def test_api_status_follows_the_decision_file_not_a_stored_copy(monkeypatch, tmp_path):
    """Computed at response time, so a changed decision is reflected and never silently stale."""
    import app.vision.api as api

    monkeypatch.setattr(api, "evidence_eligibility", lambda root: {"PSI-69": "QUARANTINED"})
    assert client.get("/api/v1/vision/evaluation").json()["evidence_eligibility"] == {"PSI-69": "QUARANTINED"}


def test_unknown_test_point_is_rejected_before_any_read():
    assert client.get("/api/v1/vision/tests/..%2f..%2fsecret").status_code in (404, 422)
    assert client.get("/api/v1/vision/tests/ABCD").status_code == 422


def test_generator_writes_the_status_into_every_output_kind():
    src = (ROOT / "backend/scripts/run_flame_vision.py").read_text(encoding="utf-8")
    # abstention summary, evaluation and full summary: three writers, each includes the field
    assert src.count('"evidence_eligibility": evidence_eligibility(ROOT)') == 3
    assert src.count('"reference_eligibility": reference_eligibility(ROOT)') == 3


def test_no_vision_code_uses_report_derived_inputs():
    """A6: dext_origin / enrichment / caption data come from NASA/TP-2015-216046 (unregistered)."""
    files = list((ROOT / "backend/app/vision").glob("*.py")) + [ROOT / "backend/scripts/run_flame_vision.py"]
    banned = re.compile(
        r"dext_origin|attach_enrichment|flex_enrichment|_captions|support_mode|Table IX|table_ix", re.I
    )
    hits = {
        f.name: sorted(set(banned.findall(f.read_text(encoding="utf-8"))))
        for f in files
        if banned.search(f.read_text(encoding="utf-8"))
    }
    # the method card may cite the report for the MEANING of D0 (documented), but must not compute from it
    hits.pop("method_card.py", None)
    assert hits == {}, hits


def test_stored_results_read_only_the_registered_psi69_table():
    ev = json.loads((OUT / "evaluation.json").read_text(encoding="utf-8"))
    assert all(t["run_id"].startswith("PSI-69-r") for t in ev["tests"])
    manifest = (
        (ROOT / "data/metadata/vision_artifact_manifest.csv").read_text(encoding="utf-8").splitlines()[1:]
    )
    data_rows = [line for line in manifest if ",reference_report," not in line]
    assert data_rows and all(line.startswith("PSI-69,") for line in data_rows)  # evidence rows: PSI-69 only
    raw = ROOT / "data/raw/PSI-69/experimental_table"
    if not raw.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    first = json.loads((OUT / "20CAL10/summary.json").read_text(encoding="utf-8"))
    assert first["nasa_reference"]["value_origin"].startswith("reported_in_source")
    assert Path(raw).is_dir()


def test_report_cross_check_is_isolated_and_labelled_unregistered():
    """Only the exploratory cross-check script reads the NASA/TP PDF; no result reads its output."""
    scripts = ROOT / "backend/scripts"
    readers = sorted(
        f.name
        for f in list(scripts.glob("*.py")) + list((ROOT / "backend/app").rglob("*.py"))
        if "pypdfium2" in f.read_text(encoding="utf-8")
    )
    assert readers == ["nasa_report_crosscheck.py"]
    gen = (scripts / "run_flame_vision.py").read_text(encoding="utf-8")
    mentions = [ln for ln in gen.splitlines() if "nasa_report_crosscheck" in ln]
    assert mentions and not any("read_text" in ln or "json.load" in ln or "open(" in ln for ln in mentions)
    out = json.loads((OUT / "nasa_report_crosscheck.json").read_text(encoding="utf-8"))
    assert out["source"]["status"].startswith("UNREGISTERED")
    assert reference_eligibility(ROOT) == UNREGISTERED_REF  # and the API exposes it as such
