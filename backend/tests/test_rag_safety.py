"""Scientific safety boundaries of the RAG/Copilot (blockers B1-B5) and the Data Platform contract."""

from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.sources import load_registry
from app.main import app
from app.rag import ids
from app.rag.config import PROJECT_ROOT
from app.rag.copilot import CopilotRequest, Status
from app.rag.eligibility import Eligibility, EligibilityPolicy, resolve
from app.rag.evaluation import flagged_sweep, load_questions, safety_metrics
from app.rag.ingest import load_flex
from app.rag.llm import ExtractiveProvider
from app.rag.measurements import EvidenceStatus
from app.rag.platform import _check, verify
from app.rag.schemas import Chunk, SearchRequest
from app.rag.service import reset_service
from tests.conftest import ScriptedProvider

INELIGIBLE = {"PSI-25", "PSI-98", "NASA-TP-2015-216046"}
HAS_PLATFORM = importlib.util.find_spec("app.data_platform") is not None


def ask(cop, q: str):
    return cop.ask(CopilotRequest(question=q, mode="bm25"))


def scripted(text: str, chunk_ref: str, quote: str) -> dict[str, Any]:
    return {
        "answer": text,
        "abstain": False,
        "tool_calls": [],
        "claims": [
            {"text": text, "citations": [{"chunk_id": chunk_ref, "quote": quote}], "tool_result_ids": []}
        ],
    }


# ------------------------------------------------------------------ B1/B2: one registry, eligibility


def test_eligibility_follows_registry_and_decisions(rag_chunks: list[Chunk]):
    pol = EligibilityPolicy(PROJECT_ROOT)
    got = {d.source_id: (d.eligibility, d.usable_as_evidence) for d in pol.all_decisions()}
    assert got["PSI-69"] == (Eligibility.PENDING_VERIFICATION, True)
    assert got["PSI-25"] == (Eligibility.ACQUIRED_BUT_EXCLUDED, False)
    assert got["PSI-98"] == (Eligibility.QUARANTINED, False)
    assert got["NASA-TP-2015-216046"] == (Eligibility.UNREGISTERED, False)
    for c in rag_chunks:  # every chunk carries its source's decision
        assert (c.eligibility, c.usable_as_evidence) == (got[c.source_id][0].value, got[c.source_id][1])


def test_decision_file_cannot_promote_and_default_is_deny():
    reg = {r.source_id: r for r in load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv")}
    yes = {"eligibility": "VERIFIED_ELIGIBLE", "usable_as_evidence": "yes", "reason": "x"}
    assert resolve("PSI-98", reg, {"PSI-98": yes}).eligibility is Eligibility.QUARANTINED  # registry wins
    d = resolve("PSI-69", reg, {"PSI-69": yes})  # registry says ACQUIRED, not VERIFIED
    assert d.eligibility is Eligibility.PENDING_VERIFICATION
    assert not resolve("PSI-69", reg, {}).usable_as_evidence  # no decision recorded -> deny
    assert resolve("NEW-DOC", reg, {"NEW-DOC": yes}).eligibility is Eligibility.UNREGISTERED


def test_nasa_tp_captions_are_never_evidence(rag_chunks: list[Chunk]):
    caps = [c for c in rag_chunks if c.source_id == "NASA-TP-2015-216046"]
    assert len(caps) == 276 and not any(c.usable_as_evidence for c in caps)
    assert all("pypdf_text_extraction_not_visually_verified" in c.quality_flags for c in caps)
    assert all(c.locator["pdf_sha256"] for c in caps)  # PDF hash kept for the future registration
    rows = [c for c in rag_chunks if c.chunk_key.startswith("PSI-69:row:")]
    # caption-derived text appears in an eligible row only as a disclosed caveat (FLEX-130 K)
    tp_rows = [c.chunk_key for c in rows if "NASA/TP" in c.text]
    assert tp_rows == ["PSI-69:row:130"]
    assert all("an unregistered source" in c.text for c in rows if "NASA/TP" in c.text)


@pytest.mark.parametrize(
    "q",
    [
        "BASS-II PMMA SIBAL flame spread glovebox",
        "SAFFIRE Cygnus smoke spacecraft fire",
        "NASA/TP-2015-216046 Appendix B figure caption vapor cloud",
        "What fuel sample material was used in BASS-II test B1?",
    ],
)
def test_search_never_returns_ineligible_chunks(retriever, q):
    res = retriever.search(SearchRequest(query=q, top_k=50))
    assert not {h.chunk.source_id for h in res.hits} & INELIGIBLE


# ------------------------------------------------------------------ B3/B4: invalid and missing values


def test_flex_114_pressure_is_flagged_invalid_never_clean(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), "What was the ambient pressure in FLEX test 114?")
    m = r.claims[0]
    assert m.measurement_status == "INVALID" and "FLAGGED INVALID" in m.text
    cm = m.citations[0].measurements[0]
    assert cm.value is None and "invalid_nonpositive_pressure" in cm.quality_flags
    assert any("ambient_pressure" in f for f in r.evidence.flagged)
    t = next(t for t in r.tool_results if t.tool == "get_flex_run")
    assert t.result["records"][0]["measurements"][0]["value"] is None


def test_flex_129_extinction_diameter_is_qualified(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), "What was the extinction diameter in FLEX test 129?")
    assert r.claims[0].measurement_status == "QUALIFIED" and "QUALIFIED" in r.claims[0].text
    assert "exceeds the initial droplet diameter" in r.claims[0].text


def test_flex_4_missing_value_is_stated_as_missing(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), "What was the extinction diameter in FLEX test 4?")
    assert r.claims[0].measurement_status == "MISSING" and "MISSING in the source" in r.claims[0].text
    assert r.claims[0].citations[0].measurements[0].value is None
    assert any("no value in the source" in x for x in r.evidence.missing)


def test_model_cannot_state_a_flagged_value_as_clean(make_copilot):
    q = "What was the ambient pressure in FLEX test 114?"
    p = ScriptedProvider(
        scripted("FLEX-114 ran at an ambient pressure of 0 mmHg.", "PSI-69:row:114", "FLEX-114")
    )
    r = ask(make_copilot(p), q)
    assert all("0 mmHg." not in c.text for c in r.claims)
    assert any("INVALID" in x for d in r.dropped_claims for x in d.reasons)


def test_model_cannot_fill_a_missing_value(make_copilot):
    q = "What was the extinction diameter in FLEX test 4?"
    # 0.21 appears in the row (O2 mole fraction), so only the missing-cell rule can stop this claim
    p = ScriptedProvider(
        scripted("FLEX-004 visible flame extinction diameter was 0.21 mm.", "PSI-69:row:004", "FLEX-004")
    )
    r = ask(make_copilot(p), q)
    assert all("0.21 mm" not in c.text for c in r.claims)
    assert any("MISSING" in x for d in r.dropped_claims for x in d.reasons)


def test_every_flagged_measurement_is_reported_with_its_status(make_copilot):
    """Sweep: all 149 missing/invalid/qualified PSI-69 cells (not only FLEX-4/114/129)."""
    res = flagged_sweep(make_copilot(ExtractiveProvider()), load_flex(PROJECT_ROOT)[2])
    assert res["n"] == 149 and res["by_status"] == {"MISSING": 111, "QUALIFIED": 37, "INVALID": 1}
    assert res["failures"] == [], res["failures"][:3]


def test_safety_suite_passes(make_copilot):
    cases = load_questions(PROJECT_ROOT / "backend/eval/rag_safety_v1.jsonl")
    res = safety_metrics(make_copilot(ExtractiveProvider()), cases)
    assert res["passed"] == res["n"] == 16, res["failures"]


def test_measurement_counts_match_the_data_platform_load():
    facts = load_flex(PROJECT_ROOT)[2]
    assert len(facts) == 2466  # docs/14_scientific_data_platform.md: 274 runs, 2,466 measurements
    assert len({f.measurement_id for f in facts}) == 2466
    c = {s: sum(f.evidence_status is s for f in facts) for s in EvidenceStatus}
    assert c[EvidenceStatus.INVALID] == 1 and c[EvidenceStatus.MISSING] == 111


# ------------------------------------------------------------------ B5: API exposure


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLAMESCOPE_RAG_CACHE", str(tmp_path))
    monkeypatch.delenv("FLAMESCOPE_RAG_ADMIN_TOKEN", raising=False)
    reset_service()
    yield TestClient(app)
    reset_service()


def test_public_routes_never_expose_ineligible_evidence(client, rag_chunks):
    bad = {"query": "SAFFIRE", "filters": {"include_quarantined": True}}
    assert client.post("/api/v1/rag/search", json=bad).status_code == 422
    bad_ask = {"question": "What did SAFFIRE measure?", "filters": {"include_quarantined": True}}
    assert client.post("/api/v1/copilot/ask", json=bad_ask).status_code == 422
    for c in [x for x in rag_chunks if x.source_id in INELIGIBLE][::40]:
        for ref in (c.chunk_id, c.chunk_key):
            r = client.get(f"/api/v1/rag/chunks/{ref}")
            assert r.status_code == 403 and "text" not in json.dumps(r.json())
    assert client.get("/api/v1/rag/admin/excluded").status_code == 404  # disabled without a token
    src = {s["source_id"]: s for s in client.get("/api/v1/rag/sources").json()}
    assert src["PSI-25"]["eligibility"] == "ACQUIRED_BUT_EXCLUDED" and "reason" not in src["PSI-25"]


def test_admin_route_shows_exclusion_reasons_with_a_token(client, monkeypatch):
    monkeypatch.setenv("FLAMESCOPE_RAG_ADMIN_TOKEN", "test-admin-token")
    assert client.get("/api/v1/rag/admin/excluded").status_code == 401
    h = {"X-FlameScope-Admin-Token": "wrong"}
    assert client.get("/api/v1/rag/admin/excluded", headers=h).status_code == 401
    h = {"X-FlameScope-Admin-Token": "test-admin-token"}
    ex = client.get("/api/v1/rag/admin/excluded", headers=h).json()
    reasons = {s["source_id"]: s["reason"] for s in ex["sources"]}
    assert "flame-spread" in reasons["PSI-25"] and "Saffire" in reasons["PSI-98"]
    assert ex["excluded_chunks"] == {"PSI-25": 139, "PSI-98": 13, "NASA-TP-2015-216046": 276}
    c = client.get("/api/v1/rag/admin/chunks/PSI-98:row:001", headers=h).json()
    assert c["eligibility"] == "QUARANTINED" and c["exclusion_reason"]


# ------------------------------------------------------------------ Data Platform contract


def test_citations_resolve_to_artifacts_and_measurement_provenance(make_copilot, rag_chunks):
    r = ask(make_copilot(ExtractiveProvider()), "What was the initial droplet diameter in FLEX-070?")
    cl = r.claims[0]
    ci = cl.citations[0]
    man = {
        row.split(",")[0]: row.split(",")
        for row in (PROJECT_ROOT / "data/metadata/artifact_manifest.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert ci.source_artifact_sha256 == man["PSI-69"][6]
    assert ci.artifact_id == ids.artifact_id(ci.source_artifact_sha256, ci.artifact_path)
    m = ci.measurements[0]
    assert m.value == 4.67 and m.unit == "mm" and m.evidence_status == "CLEAN"
    assert m.measurement_id == ids.measurement_id(
        ci.source_artifact_sha256, 70, "Droplet initial diameter; mm"
    )
    assert m.provenance == f"/api/v1/measurements/{m.measurement_id}/provenance"
    assert m.source_locator.startswith("PSI-69_Experimental table_FLEX.csv#csv_line=")
    assert r.measurement_verification in {"platform", "loader_fallback"}


def test_platform_check_rules():
    clean = SimpleNamespace(
        evidence_status="CLEAN", value=4.67, unit="mm", measurement_id="m", original_value_text="4.67"
    )
    ok_row = SimpleNamespace(usable_for_analysis=True, value=4.67, unit="mm")
    assert _check(clean, ok_row, "ACQUIRED") == []  # type: ignore[arg-type]
    assert _check(clean, ok_row, "QUARANTINED")  # type: ignore[arg-type]  # withdrawn source
    assert _check(clean, SimpleNamespace(usable_for_analysis=True, value=4.6, unit="mm"), "ACQUIRED")  # type: ignore[arg-type]
    inv = SimpleNamespace(evidence_status="INVALID", value=None, unit="mmHg")
    assert _check(inv, SimpleNamespace(usable_for_analysis=True, value=0, unit="mmHg"), "ACQUIRED")  # type: ignore[arg-type]
    miss = SimpleNamespace(evidence_status="MISSING", value=None, unit="mm")
    assert _check(miss, SimpleNamespace(usable_for_analysis=False, value=1.0, unit="mm"), "ACQUIRED")  # type: ignore[arg-type]


@pytest.mark.skipif(HAS_PLATFORM, reason="platform package present: covered by the combined tests")
def test_without_platform_numbers_are_marked_unverified(monkeypatch):
    monkeypatch.delenv("FLAMESCOPE_DATABASE_URL", raising=False)
    ref = load_flex(PROJECT_ROOT)[2][0]
    v = verify([SimpleNamespace(measurement_id=ref.measurement_id)])  # type: ignore[list-item]
    assert v.mode == "loader_fallback" and "not checked" in v.detail


def test_cross_regime_comparisons_stay_blocked(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    for q in (
        "Compare the burning rate of FLEX heptane droplets with BASS-II solid samples",
        "Is the FLEX droplet burning rate higher than the SAFFIRE flame spread rate?",
    ):
        r = ask(cop, q)
        assert r.status is Status.COMPARISON_BLOCKED and not r.claims
