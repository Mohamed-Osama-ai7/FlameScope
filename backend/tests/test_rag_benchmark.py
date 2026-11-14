"""Golden set v3, benchmark metric definitions and regression floors (docs/18_rag_benchmark.md)."""

from __future__ import annotations

from collections import Counter

import pytest

from app.rag.benchmark import benchmark, summarise
from app.rag.config import PROJECT_ROOT
from app.rag.copilot import ScientificCopilot
from app.rag.evaluation import load_questions, verify_gold
from app.rag.llm import ExtractiveProvider
from app.rag.query_analysis import analyse

GOLDEN = PROJECT_ROOT / "backend/eval/rag_golden_v3.jsonl"


def test_golden_set_is_valid_and_backed_by_eligible_evidence(rag_chunks):
    items = load_questions(GOLDEN)
    assert 30 <= len(items) <= 50 and len({q["id"] for q in items}) == len(items)
    assert verify_gold(items, rag_chunks) == []  # verbatim quotes in usable gold chunks
    cats = Counter(q["category"] for q in items)
    assert set(cats) == {
        "direct",
        "comparison",
        "scientific",
        "invalid_comparison",
        "unsupported",
        "ineligible_source",
    }
    assert {q["split"] for q in items} == {"dev", "test"}
    keys = {c.chunk_key: c for c in rag_chunks}
    for q in items:
        assert all(keys[g].source_id == "PSI-69" for g in q["gold_chunks"])  # approved evidence only


def _row(**kw):
    base = {
        "id": "X",
        "split": "dev",
        "category": "direct",
        "expected": "answered",
        "got": "answered",
        "reason": None,
        "status_ok": True,
        "refused": False,
        "should_refuse": False,
        "cited": [],
        "gold": [],
        "citation_gold": 0,
        "citations": 0,
        "gold_cited": 0,
        "n_gold": 0,
        "answer_support": False,
        "grounded": 0,
        "claims": 0,
        "verbatim": True,
        "ineligible": 0,
    }
    return base | kw


def test_abstention_and_citation_metric_math():
    rows = [
        _row(refused=True, should_refuse=True, status_ok=True),  # correct refusal
        _row(refused=True, should_refuse=False, status_ok=False),  # false abstention
        _row(refused=False, should_refuse=True, status_ok=False),  # missed abstention
        _row(citations=4, citation_gold=1, n_gold=2, gold_cited=1, claims=2, grounded=2),
    ]
    s = summarise(rows)
    assert s["abstention"] == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "false_abstentions": 1,
        "missed_abstentions": 1,
    }
    assert s["citation_precision"] == 0.25 and s["citation_recall"] == 0.5 and s["grounding"] == 1.0
    assert s["status_accuracy"] == 0.5


def test_dev_derived_query_analysis_fixes():
    assert analyse("How large was the droplet at ignition in FLEX-033?").variables == [
        "initial_droplet_diameter"
    ]
    assert (
        "initial_droplet_diameter"
        in analyse("Which started with the larger droplet, FLEX-225 or FLEX-261?").variables
    )
    toks = analyse("Compare the burn times of FLEX-033 and FLEX-122.").content_tokens
    assert "compare" not in toks and "burn" in toks
    # cross-regime comparisons are still detected (cue words only leave the content-term check)
    assert analyse("Compare FLEX droplets with BASS-II samples").cross_regime_comparison


@pytest.fixture(scope="module")
def result(retriever):
    return benchmark(retriever, ScientificCopilot(retriever, ExtractiveProvider()), load_questions(GOLDEN))


def test_benchmark_regression_floors(result):
    """Floors at the measured values (benchmark_v3_after_dev_tuning.json); a drop is a regression."""
    r, c = result["all"]["retrieval"], result["all"]["copilot"]
    assert r["n"] == 20 and r["recall"]["@5"] == 1.0 and r["mrr"] >= 0.975
    assert c["ineligible_citations"] == 0 and c["grounding"] == 1.0 and c["verbatim_citations"] == 1.0
    cats = c["status_accuracy_by_category"]
    assert cats["ineligible_source"] == "6/6" and cats["invalid_comparison"] == "3/3"
    assert c["abstention"]["recall"] >= 0.9375 and c["status_accuracy"] >= 0.8611
    assert c["comparison_completeness"] == 1.0


def test_benchmark_is_deterministic(retriever, result):
    again = benchmark(retriever, ScientificCopilot(retriever, ExtractiveProvider()), load_questions(GOLDEN))
    assert again == result
