"""Reproducible evaluation: retrieval metrics, end-to-end Copilot metrics and gold-label verification.

Datasets: backend/eval/rag_questions_v2.jsonl (v1 kept for the historical results) and the safety suite
backend/eval/rag_safety_v1.jsonl; `flagged_sweep` asks about EVERY missing/invalid/qualified PSI-69 cell.
Every answerable question has gold chunk keys AND a verbatim gold
quote that is checked against the chunk text, so labels cannot silently drift from the corpus). The split
(dev / test) is fixed in the file; thresholds are tuned on dev only.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.rag.bm25 import tokenize
from app.rag.citations import numbers
from app.rag.copilot import CopilotRequest, ScientificCopilot, Status
from app.rag.measurements import MARKERS, EvidenceStatus, MeasurementFact
from app.rag.retriever import HybridRetriever
from app.rag.schemas import Chunk, SearchRequest

KS = (1, 3, 5, 10)
REFUSAL = {Status.ABSTAINED.value, Status.COMPARISON_BLOCKED.value}


def load_questions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ws(s: str) -> str:
    return " ".join(s.split())


def verify_gold(questions: list[dict[str, Any]], chunks: list[Chunk]) -> list[str]:
    """Return a list of problems (empty = every gold label is backed by a verbatim span in the corpus)."""
    by_id = {c.chunk_key: c for c in chunks}  # gold labels use readable keys
    problems: list[str] = []
    for q in questions:
        if not q["answerable"]:
            continue
        for g in q["gold_chunks"]:
            if g not in by_id:
                problems.append(f"{q['id']}: gold chunk {g} does not exist")
        quote = _ws(q["gold_quote"])
        if not any(quote in _ws(by_id[g].text) for g in q["gold_chunks"] if g in by_id):
            problems.append(f"{q['id']}: gold quote is not a verbatim span of any gold chunk")
        if any(g in by_id and not by_id[g].usable_as_evidence for g in q["gold_chunks"]):
            problems.append(f"{q['id']}: gold chunk is not usable evidence")
    return problems


def _ndcg(rels: list[int], n_gold: int, k: int) -> float:
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(n_gold, k)))
    return dcg / ideal if ideal else 0.0


def _pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, math.ceil(p * len(s)) - 1))] if s else float("nan")


def retrieval_metrics(
    retriever: HybridRetriever, questions: list[dict[str, Any]], mode: str, rerank: bool = False
) -> dict[str, Any]:
    """Query-only retrieval (no metadata filters) over the answerable questions."""
    qs = [q for q in questions if q["answerable"]]
    rec: dict[int, list[float]] = {k: [] for k in KS}
    hit: dict[int, list[float]] = {k: [] for k in KS}
    mrr: list[float] = []
    ndcg: list[float] = []
    lat: list[float] = []
    failures: list[dict[str, Any]] = []
    for q in qs:
        t0 = time.perf_counter()
        res = retriever.search(SearchRequest(query=q["question"], top_k=10, mode=mode, rerank=rerank))  # type: ignore[arg-type]
        lat.append((time.perf_counter() - t0) * 1000)
        ids = [h.chunk.chunk_key for h in res.hits]
        gold = set(q["gold_chunks"])
        for k in KS:
            found = gold & set(ids[:k])
            rec[k].append(len(found) / len(gold))
            hit[k].append(1.0 if found else 0.0)
        first = next((i for i, c in enumerate(ids, 1) if c in gold), None)
        mrr.append(1.0 / first if first else 0.0)
        ndcg.append(_ndcg([1 if c in gold else 0 for c in ids], len(gold), 10))
        if not (gold & set(ids[:5])):
            failures.append({"id": q["id"], "question": q["question"], "gold": sorted(gold), "top5": ids[:5]})
    m = statistics.fmean
    return {
        "n": len(qs),
        "recall": {f"@{k}": round(m(rec[k]), 4) for k in KS},
        "hit_rate": {f"@{k}": round(m(hit[k]), 4) for k in KS},
        "mrr": round(m(mrr), 4),
        "ndcg@10": round(m(ndcg), 4),
        "latency_ms": {"median": round(statistics.median(lat), 2), "p95": round(_pct(lat, 0.95), 2)},
        "failures_top5": failures,
    }


def _faithful(claim_text: str, cites: list[Any]) -> float:
    """Lexical-support proxy: share of the claim's content tokens present in its cited quotes (NOT an
    entailment judge). Also requires every number in the claim to occur in the cited quotes."""
    ct = set(tokenize(claim_text))
    qt = set(tokenize(" ".join(c.quote for c in cites)))
    if not ct:
        return 0.0
    nums_ok = numbers(claim_text) <= numbers(" ".join(c.quote for c in cites))
    return (len(ct & qt) / len(ct)) if nums_ok else 0.0


def copilot_metrics(
    copilot: ScientificCopilot, questions: list[dict[str, Any]], mode: str, rerank: bool = False
) -> dict[str, Any]:
    ans = [q for q in questions if q["answerable"]]
    una = [q for q in questions if not q["answerable"]]
    rows: list[dict[str, Any]] = []
    for q in questions:
        r = copilot.ask(CopilotRequest(question=q["question"], mode=mode, rerank=rerank))  # type: ignore[arg-type]
        rows.append({"q": q, "r": r})
    a_rows = [x for x in rows if x["q"]["answerable"]]
    u_rows = [x for x in rows if not x["q"]["answerable"]]
    answered = [x for x in a_rows if x["r"].status.value not in REFUSAL]
    cite_ok, strict_ok, support, faith, dropped, total = [], [], [], [], 0, 0
    for x in answered:
        r, q = x["r"], x["q"]
        gold = set(q["gold_chunks"])
        cited = [c.chunk_key for cl in r.claims for c in cl.citations]
        cite_ok.append(1.0 if gold & set(cited) else 0.0)
        strict_ok.append(1.0 if cited and set(cited) <= gold else 0.0)
        support.append(1.0 if _ws(q["gold_quote"]) in _ws(r.answer) else 0.0)
        faith += [_faithful(cl.text, cl.citations) for cl in r.claims if cl.citations]
    for x in rows:
        dropped += len(x["r"].dropped_claims)
        total += len(x["r"].claims) + len(x["r"].dropped_claims)
    m = statistics.fmean
    status_match = [1.0 if x["r"].status.value == x["q"]["expected_status"] else 0.0 for x in rows]
    return {
        "n_answerable": len(ans),
        "n_unanswerable": len(una),
        "answer_rate_on_answerable": round(len(answered) / len(a_rows), 4) if a_rows else None,
        "false_abstention_rate": round(1 - len(answered) / len(a_rows), 4) if a_rows else None,
        "correct_abstention_rate_on_unanswerable": round(
            sum(1 for x in u_rows if x["r"].status.value in REFUSAL) / len(u_rows), 4
        )
        if u_rows
        else None,
        "wrong_answer_on_unanswerable": sum(1 for x in u_rows if x["r"].status.value not in REFUSAL),
        "citation_correctness_any_gold": round(m(cite_ok), 4) if cite_ok else None,
        "citation_precision_all_gold": round(m(strict_ok), 4) if strict_ok else None,
        "answer_contains_gold_quote": round(m(support), 4) if support else None,
        "faithfulness_lexical_proxy": round(m(faith), 4) if faith else None,
        "claims_failing_validation": dropped,
        "claims_generated": total,
        "expected_status_match": round(m(status_match), 4),
        "problems": [
            {
                "id": x["q"]["id"],
                "expected": x["q"]["expected_status"],
                "got": x["r"].status.value,
                "reason": x["r"].abstention_reason,
            }
            for x in rows
            if x["r"].status.value != x["q"]["expected_status"]
        ],
    }


def split(questions: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return questions if name == "all" else [q for q in questions if q["split"] == name]


def run_all(
    retriever_factory: Callable[[str, str], HybridRetriever],
    copilot_factory: Callable[[HybridRetriever], ScientificCopilot],
    questions: list[dict[str, Any]],
    configs: list[tuple[str, str, str, bool]],
) -> dict[str, Any]:
    """configs: (label, dense_backend, mode, rerank). Returns metrics per config and split."""
    out: dict[str, Any] = {}
    for label, backend, mode, rerank in configs:
        ret = retriever_factory(backend, mode)
        cop = copilot_factory(ret)
        out[label] = {"dense_backend": ret.dense_backend, "mode": mode, "rerank": rerank, "splits": {}}
        for sp in ("dev", "test", "all"):
            qs = split(questions, sp)
            out[label]["splits"][sp] = {
                "retrieval": retrieval_metrics(ret, qs, mode, rerank),
                "copilot": copilot_metrics(cop, qs, mode, rerank),
            }
    return out


def _measurement_ok(r: Any, run_id: str, variable: str, status: str) -> tuple[bool, str]:
    """The answer must carry a claim for that cell, with the right status and its marker."""
    marker = MARKERS.get(EvidenceStatus(status), "MISSING" if status == "MISSING" else "")
    for cl in r.claims:
        for ci in cl.citations:
            for m in ci.measurements:
                if m.run_id == run_id and m.variable == variable:
                    if m.evidence_status != status:
                        return False, f"status {m.evidence_status} != {status}"
                    if marker and marker not in cl.text:
                        return False, f"claim lacks marker '{marker}'"
                    if status in ("INVALID", "MISSING") and m.value is not None:
                        return False, "a value was exposed for an invalid/missing cell"
                    return True, ""
    return False, "no claim cites that measurement"


def safety_metrics(copilot: ScientificCopilot, cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for c in cases:
        r = copilot.ask(CopilotRequest(question=c["question"], mode="bm25"))
        ok, why = r.status.value == c["expect_status"], ""
        if not ok:
            why = f"status {r.status.value} != {c['expect_status']}"
        if ok and c.get("expect_reason") and c["expect_reason"] not in (r.abstention_reason or ""):
            ok, why = False, f"reason lacks {c['expect_reason']}"
        if ok and c.get("expect_measurement"):
            e = c["expect_measurement"]
            ok, why = _measurement_ok(r, e["run_id"], e["variable"], e["evidence_status"])
        cited = {ci.source_id for cl in r.claims for ci in cl.citations}
        if ok and cited & {"PSI-25", "PSI-98", "NASA-TP-2015-216046"}:
            ok, why = False, f"cited ineligible source(s) {sorted(cited)}"
        rows.append(
            {
                "id": c["id"],
                "case": c["case"],
                "pass": ok,
                "why": why,
                "status": r.status.value,
                "measurement_verification": r.measurement_verification,
            }
        )
    by_case: dict[str, list[bool]] = {}
    for x in rows:
        by_case.setdefault(x["case"], []).append(x["pass"])
    return {
        "n": len(rows),
        "passed": sum(x["pass"] for x in rows),
        "by_case": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_case.items())},
        "failures": [x for x in rows if not x["pass"]],
    }


def flagged_sweep(copilot: ScientificCopilot, facts: list[MeasurementFact]) -> dict[str, Any]:
    """Ask about every non-CLEAN PSI-69 cell; each must come back with its status and marker."""
    flagged = [f for f in facts if f.evidence_status is not EvidenceStatus.CLEAN]
    fails = []
    for f in flagged:
        r = copilot.ask(CopilotRequest(question=f"What was the {f.label} in {f.experiment_id}?", mode="bm25"))
        ok, why = _measurement_ok(r, f.run_id, f.variable, f.evidence_status.value)
        if not ok:
            fails.append(
                {
                    "measurement_id": f.measurement_id,
                    "run_id": f.run_id,
                    "variable": f.variable,
                    "status": f.evidence_status.value,
                    "copilot_status": r.status.value,
                    "why": why,
                }
            )
    counts: dict[str, int] = {}
    for f in flagged:
        counts[f.evidence_status.value] = counts.get(f.evidence_status.value, 0) + 1
    return {"n": len(flagged), "by_status": counts, "passed": len(flagged) - len(fails), "failures": fails}
