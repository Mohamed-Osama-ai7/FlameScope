"""Release gates: source eligibility, approval wording, hashes, provenance and quality-flag preservation.

These tests encode the CURRENT scientific decisions (data/metadata/source_eligibility.csv, registry);
a decision change by the scientific owner must update them explicitly. Raw-data tests skip only when the
gitignored file is absent; FLAMESCOPE_REQUIRE_RAW_DATA=1 turns such skips into failures.
"""

from __future__ import annotations

import csv
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.domain.sources import VerificationStatus, load_registry
from app.main import app
from app.rag.config import PROJECT_ROOT
from app.rag.copilot import CopilotRequest
from app.rag.eligibility import Eligibility, EligibilityPolicy
from app.rag.llm import ExtractiveProvider
from app.rag.tools import run_tool

META = PROJECT_ROOT / "data/metadata"
DATASET = PROJECT_ROOT / "frontend/public/data/flex_lab_dataset_v0.2.0.json"
INELIGIBLE = {"PSI-25", "PSI-98", "NASA-TP-2015-216046", "CHALLENGE-RESOURCE-01"}


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict[str, dict[str, str]]:
    with (META / "artifact_manifest.csv").open(encoding="utf-8", newline="") as fh:
        return {r["source_id"]: r for r in csv.DictReader(fh)}


# ------------------------------------------------------------------ source states


def test_every_source_state_is_consistent_and_nothing_is_approved():
    pol = EligibilityPolicy(PROJECT_ROOT)
    reg = {r.source_id: r for r in load_registry(META / "source_registry.csv")}
    decided = {d.source_id: d for d in pol.all_decisions()}
    assert set(reg) <= set(decided)  # every registered source has a resolved decision
    for d in decided.values():
        if d.eligibility is Eligibility.VERIFIED_ELIGIBLE:
            assert reg[d.source_id].verification_status is VerificationStatus.VERIFIED
        if d.registry_status in {"QUARANTINED", "RESOURCE_RECORDED", ""}:
            assert not d.usable_as_evidence, d.source_id
    assert {s for s, d in decided.items() if d.usable_as_evidence} == {"PSI-69"}
    assert decided["PSI-69"].eligibility is Eligibility.PENDING_VERIFICATION  # not approved
    assert reg["CHALLENGE-RESOURCE-01"].verification_status is VerificationStatus.RESOURCE_RECORDED
    assert not any(r.verification_status is VerificationStatus.VERIFIED for r in reg.values())


def test_status_endpoint_respects_evidence_decisions():
    s = TestClient(app).get("/api/v1/status").json()
    assert s["sources_usable_as_evidence"] == ["PSI-69"]  # PSI-25 is ACQUIRED but excluded
    assert s["evidence_eligibility"]["PSI-25"] == "ACQUIRED_BUT_EXCLUDED"
    assert s["evidence_eligibility"]["PSI-69"] == "PENDING_VERIFICATION"


def _series(source_id: str) -> dict:
    t = [0.0, 1.0, 2.0, 3.0]
    return {
        "run_id": "r",
        "regime": "flex_droplet",
        "fuel": "Heptane",
        "time_unit": "s",
        "diameter_unit": "mm",
        "window_selection": "test",
        "time_s": t,
        "diameter_mm": [(4.0 - 0.5 * x) ** 0.5 for x in t],
        "provenance": {"source_id": source_id, "source_locator": "synthetic", "extraction_method": "test"},
    }


@pytest.mark.parametrize("sid", sorted(INELIGIBLE - {"NASA-TP-2015-216046"}))
def test_analysis_endpoint_refuses_ineligible_registered_sources(sid):
    r = TestClient(app).post("/api/v1/analysis/droplet/burning-rate-constant", json=_series(sid))
    assert r.status_code == 422, sid


def test_analysis_endpoint_accepts_pending_and_flags_unregistered():
    c = TestClient(app)
    assert c.post("/api/v1/analysis/droplet/burning-rate-constant", json=_series("PSI-69")).status_code == 200
    r = c.post("/api/v1/analysis/droplet/burning-rate-constant", json=_series("NASA-TP-2015-216046"))
    assert r.status_code == 200 and any("not traceable" in w for w in r.json()["warnings"])


def test_copilot_fit_tool_refuses_excluded_source():
    assert not run_tool("T1", "fit_burning_rate_constant", _series("PSI-25")).ok
    assert run_tool("T2", "fit_burning_rate_constant", _series("PSI-69")).ok


def test_copilot_never_cites_ineligible_or_claims_approval(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    for q in (
        "What hardware housed the BASS-II experiments?",
        "What did SAFFIRE-I measure?",
        "Which hardware housed the FLEX droplet investigation?",
        "What K was reported for FLEX-001?",
    ):
        r = cop.ask(CopilotRequest(question=q))
        cites = [c for cl in r.claims for c in cl.citations]
        assert not {c.source_id for c in cites} & INELIGIBLE, q
        assert all(c.eligibility == "PENDING_VERIFICATION" for c in cites), q
        assert "approved" not in r.answer.lower() and "VERIFIED_ELIGIBLE" not in json.dumps(r.model_dump()), q


def test_lab_export_makes_no_approval_claim():
    text = DATASET.read_text(encoding="utf-8")
    assert "approved" not in text.lower() and "VERIFIED_ELIGIBLE" not in text
    assert '"VERIFIED"' not in text
    assert "not visually verified" in text  # caption-derived fields carry their caveat


# ------------------------------------------------------------------ hashes and provenance


def test_registry_manifest_and_raw_hashes_agree():
    reg = {r.source_id: r for r in load_registry(META / "source_registry.csv")}
    for sid, row in manifest().items():
        assert reg[sid].sha256 == row["sha256"], sid
        path = PROJECT_ROOT / row["relative_path"]
        if not path.exists():
            pytest.skip(f"{row['relative_path']} not present (gitignored)")
        assert sha(path) == row["sha256"] and path.stat().st_size == int(row["byte_size"]), sid


def test_lab_export_provenance_hashes_match_artifacts():
    prov = json.loads(DATASET.read_text(encoding="utf-8"))["provenance"]
    assert prov["raw_sha256"] == manifest()["PSI-69"]["sha256"]
    assert prov["enrichment_sha256"] == sha(PROJECT_ROOT / "data/derived/flex_enrichment_v1.csv")
    assert prov["captions_sha256"] == sha(PROJECT_ROOT / "data/derived/flex_enrichment_v1_captions.json")
    assert prov["analysis_summary_sha256"] == sha(PROJECT_ROOT / "reports/flex_run_level_v0.2/summary.json")
    caps = json.loads(
        (PROJECT_ROOT / "data/derived/flex_enrichment_v1_captions.json").read_text(encoding="utf-8")
    )
    assert prov["report_pdf_sha256"] == caps["source"]["pdf_sha256"]  # same PDF hash everywhere


def test_quality_flags_and_missing_values_survive_every_layer(rag_chunks):
    # lab export
    recs = {r["psi_row"]: r for r in json.loads(DATASET.read_text(encoding="utf-8"))["records"]}
    assert "invalid_nonpositive_pressure" in recs[114]["field_flags"]["ambient_pressure"]
    assert recs[4]["field_flags"]["extinction_diameter"] == ["missing_blank"]
    assert recs[4]["values"]["extinction_diameter"] is None
    # RAG chunks (what the Copilot can cite)
    rows = {c.chunk_key: c for c in rag_chunks}
    m = {x.variable: x for x in rows["PSI-69:row:114"].measurements}
    assert m["ambient_pressure"].evidence_status == "INVALID" and m["ambient_pressure"].value == 0.0
    m = {x.variable: x for x in rows["PSI-69:row:004"].measurements}
    assert m["extinction_diameter"].evidence_status == "MISSING" and m["extinction_diameter"].value is None
    m = {x.variable: x for x in rows["PSI-69:row:223"].measurements}
    assert m["burn_time"].evidence_status == "QUALIFIED" and "approximate" in m["burn_time"].quality_flags


def test_platform_extraction_preserves_flags_and_provenance():
    pytest.importorskip("app.data_platform")
    from app.data_platform.extract_flex import extract
    from app.domain.sources import find_source

    raw = PROJECT_ROOT / manifest()["PSI-69"]["relative_path"]
    if not raw.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    src = find_source(load_registry(META / "source_registry.csv"), "PSI-69")
    b = extract(PROJECT_ROOT, src, META / "artifact_manifest.csv")
    by = {(m["run_id"], m["variable_name"]): m for m in b.measurements}
    p = by[("PSI-69-r114", "ambient_pressure")]
    assert p["usable_for_analysis"] is False and "invalid_nonpositive_pressure" in p["quality_flags"]
    e = by[("PSI-69-r004", "extinction_diameter")]
    assert e["value"] is None and e["value_status"] == "missing"
    t = by[("PSI-69-r223", "burn_time")]
    assert t["value_status"] == "approximate" and t["original_value_text"] == "~6"
    assert all(m["source_locator"].startswith(manifest()["PSI-69"]["file_name"]) for m in b.measurements)
    assert b.artifact["sha256"] == manifest()["PSI-69"]["sha256"]
