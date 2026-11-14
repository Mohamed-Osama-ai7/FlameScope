"""Answer-level Copilot evaluation (v4): data validity, metric math, fixes, regression floors (docs/19)."""

from __future__ import annotations

from collections import Counter

import pytest

from app.rag.answer_eval import evaluate_item, summarise
from app.rag.config import PROJECT_ROOT
from app.rag.copilot import CopilotRequest, ScientificCopilot, Status
from app.rag.evaluation import load_questions, verify_gold
from app.rag.llm import ExtractiveProvider
from app.rag.query_analysis import analyse

V4 = PROJECT_ROOT / "backend/eval/copilot_answers_v4.jsonl"


def test_v4_set_is_blind_valid_and_separate_from_v3(rag_chunks):
    items = load_questions(V4)
    assert verify_gold(items, rag_chunks) == []
    keys = {c.chunk_key: c for c in rag_chunks}
    for q in items:
        for f in q.get("facts", []):
            assert any(f in keys[g].text for g in q["gold_chunks"]), (q["id"], f)
    v3 = load_questions(PROJECT_ROOT / "backend/eval/rag_golden_v3.jsonl")
    v3_rows = {g for q in v3 for g in q["gold_chunks"] if ":row:" in g}
    assert not v3_rows & {g for q in items for g in q["gold_chunks"]}  # no overlap with v3 table rows
    assert Counter(q["split"] for q in items) == {"diagnostic": 17, "holdout": 17}


def _row(**kw):
    base = {
        "id": "X",
        "split": "diagnostic",
        "category": "numeric",
        "question": "q",
        "expected": "answered",
        "got": "answered",
        "status_ok": True,
        "abstention_reason": None,
        "refused": False,
        "should_refuse": False,
        "facts": ["F"],
        "facts_found": ["F"],
        "factual_correct": True,
        "claims": [
            {
                "text": "c",
                "cited": ["k"],
                "supported": True,
                "on_gold": True,
                "measurement_status": None,
                "ineligible": 0,
            }
        ],
        "answer": "F",
    }
    return base | kw


def test_summary_math():
    rows = [
        _row(),
        _row(got="abstained", status_ok=False, refused=True, factual_correct=None, facts_found=[], claims=[]),
        _row(
            claims=[
                {
                    "text": "x",
                    "cited": ["k2"],
                    "supported": False,
                    "on_gold": False,
                    "measurement_status": None,
                    "ineligible": 1,
                }
            ],
            factual_correct=False,
            facts_found=[],
        ),
    ]
    s = summarise(rows)
    assert s["factual_accuracy"] == pytest.approx(1 / 3, abs=1e-4)  # a refusal is not a correct answer
    assert s["unsupported_claims"] == 1 and s["ineligible_citations"] == 1 and s["off_target_claims"] == 1
    assert s["abstention"]["false_abstentions"] == 1


def test_cue_order_extinction_before_initial_diameter():
    # v4 diagnostic A03 was answered with D0 while the initial-diameter cue came first
    assert analyse("How big was the droplet when its flame went out in FLEX-086?").variables == [
        "extinction_diameter"
    ]
    assert analyse("How large was the droplet at ignition in FLEX-033?").variables == [
        "initial_droplet_diameter"
    ]
    assert analyse("How long did the flame last in FLEX-161?").variables == ["burn_time"]
    assert analyse("How many seconds did FLEX-099 burn?").variables == ["burn_time"]


def test_resolved_measurement_skips_only_the_coverage_gate(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    r = cop.ask(CopilotRequest(question="How big was the droplet when its flame went out in FLEX-086?"))
    assert r.status is Status.ANSWERED and "FLEX-086 visible flame extinction diameter: 2.56 mm" in r.answer
    # an unrecognised quantity for a named test still abstains (no variable resolved)
    assert (
        cop.ask(CopilotRequest(question="What was the soot temperature in FLEX-187?")).status
        is Status.ABSTAINED
    )
    # the out-of-vocabulary gate still applies when a variable is resolved
    r = cop.ask(CopilotRequest(question="What was the electrode pressure in FLEX-094?"))
    assert r.status is Status.ABSTAINED


@pytest.fixture(scope="module")
def results(retriever):
    cop = ScientificCopilot(retriever, ExtractiveProvider())
    items = load_questions(V4)
    return {
        sp: summarise([evaluate_item(cop, q) for q in items if q["split"] == sp])
        for sp in ("diagnostic", "holdout")
    }


def test_answer_level_regression_floors(results):
    """Floors at the measured values (reports/copilot_eval/answers_v4_*_final.json)."""
    for sp in ("diagnostic", "holdout"):
        s = results[sp]
        assert s["claim_support_rate"] == 1.0 and s["unsupported_claims"] == 0, sp
        assert s["ineligible_citations"] == 0 and s["factual_accuracy"] == 1.0, sp
    assert results["diagnostic"]["status_accuracy"] == 1.0
    assert results["holdout"]["status_accuracy"] >= 0.8824  # after the A34 fix (post-holdout)


def test_run_questions_about_absent_fuels_abstain(make_copilot):
    """v4 holdout A34 (post-holdout fix): publication titles must not stand in for FLEX runs."""
    cop = make_copilot(ExtractiveProvider())
    for q in ("Which FLEX test used a propanol droplet?", "Which FLEX run burned ethanol?"):
        r = cop.ask(CopilotRequest(question=q))
        assert r.status is Status.ABSTAINED and "no table row for fuel" in r.abstention_reason
    # the publication list itself can still be asked about
    r = cop.ask(CopilotRequest(question="Which publication studied propanol droplet flammability?"))
    assert r.status is Status.ANSWERED and "PROPANOL DROPLET FLAMMABILITY" in r.answer
