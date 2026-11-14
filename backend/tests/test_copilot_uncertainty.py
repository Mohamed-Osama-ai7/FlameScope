"""Uncertainty-aware answering (set v5): taxonomy, evidence support, gates, set validity, floors (docs/20)."""

from __future__ import annotations

import pytest

from app.rag.config import PROJECT_ROOT
from app.rag.copilot import CopilotRequest, CopilotResponse, ScientificCopilot, Status
from app.rag.evaluation import load_questions, verify_gold
from app.rag.llm import ExtractiveProvider
from app.rag.uncertainty_eval import evaluate_item, summarise

V5 = PROJECT_ROOT / "backend/eval/copilot_uncertainty_v5.jsonl"


def keys(cop, q: str) -> tuple[Status, set[str]]:
    r = cop.ask(CopilotRequest(question=q))
    return r.status, {u.key for u in r.uncertainty}


def test_no_confidence_score_is_exposed():
    assert not {f for f in CopilotResponse.model_fields if "confidence" in f or "probab" in f}


def test_taxonomy_on_non_v5_questions(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    st, k = keys(cop, "What K was reported for FLEX-001?")
    assert st is Status.ANSWERED
    assert {
        "measurement:no_reported_uncertainty",
        "model:reported_fit_value",
        "data:source_pending_verification",
    } <= k
    st, k = keys(cop, "What was the extinction diameter in FLEX test 4?")
    assert "data:missing_value" in k and "measurement:no_reported_uncertainty" not in k
    assert keys(cop, "What was the ambient pressure in FLEX test 114?")[1] >= {"measurement:invalid_value"}
    assert (
        "data:duplicate_identifier_records"
        in keys(cop, "Which records share the source identifier 193F001?")[1]
    )
    assert keys(cop, "What hardware housed the BASS-II experiments?") == (
        Status.ABSTAINED,
        {"data:ineligible_source"},
    )
    st, k = keys(
        cop, "Compare the burning-rate constant of FLEX heptane with the flame spread rate in BASS-II."
    )
    assert st is Status.COMPARISON_BLOCKED and k == {"model:incompatible_regimes"}


def test_extrapolation_gate(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    for q in (
        "What will the burn time of heptane droplets be at 3 atm?",
        "Estimate the extinction diameter of a 6 mm methanol droplet.",
    ):
        st, k = keys(cop, q)
        assert st is Status.ABSTAINED and "model:extrapolation_refused" in k, q
    # a measured value for a named run is unaffected
    assert keys(cop, "What burn time was reported for FLEX test 1?")[0] is Status.ANSWERED


def test_every_uncertainty_item_rests_on_evidence_in_the_response(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    for q in (
        "What K was reported for FLEX-001?",
        "What was the extinction diameter in FLEX test 4?",
        "Which records share the source identifier 193F001?",
    ):
        r = cop.ask(CopilotRequest(question=q))
        cited = {m.measurement_id for cl in r.claims for c in cl.citations for m in c.measurements}
        ids = set(r.retrieved_chunk_ids) | set(r.source_eligibility) | cited
        for u in r.uncertainty:
            assert all(e in ids for e in u.evidence), (q, u.key)


def test_v5_is_valid_and_unseen(rag_chunks):
    items = load_questions(V5)
    assert verify_gold(items, rag_chunks) == []
    used = set()
    for f in ("rag_golden_v3.jsonl", "copilot_answers_v4.jsonl"):
        for q in load_questions(PROJECT_ROOT / "backend/eval" / f):
            used |= set(q.get("gold_chunks") or [])
    assert not used & {g for q in items for g in q["gold_chunks"]}  # no gold overlap with v3/v4
    assert {q["split"] for q in items} == {"diagnostic", "holdout"}


@pytest.fixture(scope="module")
def results(retriever):
    cop = ScientificCopilot(retriever, ExtractiveProvider())
    items = load_questions(V5)
    return {
        sp: summarise([evaluate_item(cop, q) for q in items if q["split"] == sp])
        for sp in ("diagnostic", "holdout")
    }


def test_v5_regression_floors(results):
    """Floors at the measured values (reports/copilot_eval/uncertainty_v5_*_final.json)."""
    for sp, s in results.items():
        assert s["status_accuracy"] == 1.0 and s["factual_accuracy"] == 1.0, sp
        assert s["uncertainty_code_recall"] == 1.0 and s["unsupported_explanations"] == 0, sp
        assert s["contradictory_codes"] == 0 and s["forbidden_terms"] == 0, sp
        assert s["selective"]["risk_on_unanswerable"] == 0.0, sp
