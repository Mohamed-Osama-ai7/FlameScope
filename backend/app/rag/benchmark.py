"""Scientific benchmark of retrieval and the Copilot on a golden set (backend/eval/rag_golden_v3.jsonl).

Retrieval (answerable items, query only, no metadata filters), for K in (1, 3, 5, 10):
  Precision@K = |gold ∩ top-K| / K ; Recall@K = |gold ∩ top-K| / |gold| ; MRR = mean 1/rank of the first gold;
  nDCG@10 with binary relevance.
Copilot (all items):
  status accuracy (answered / abstained / comparison_blocked as expected), per category;
  abstention: precision, recall and F1 of "refused" (abstained or comparison_blocked) vs expected refusal;
  citation precision = gold citations / all citations; citation recall = gold chunks cited / gold chunks;
  answer support = gold quote contained in the answer; comparison completeness = all gold rows cited;
  grounding (recomputed independently of the validator): each citation quote is a verbatim span of a usable,
  retrieved chunk and every number in a claim occurs in its cited quotes or in a tool result;
  ineligible citations: citations of sources that are not usable evidence (must be 0).
All definitions are deterministic; nothing is sampled. The extractive provider is used; no LLM.
"""

from __future__ import annotations

import json
import math
import statistics
from typing import Any

from app.rag.citations import numbers
from app.rag.copilot import CopilotRequest, ScientificCopilot
from app.rag.retriever import HybridRetriever
from app.rag.schemas import SearchRequest

KS = (1, 3, 5, 10)
REFUSED = {"abstained", "comparison_blocked"}


def _ws(s: str) -> str:
    return " ".join(s.split())


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def retrieval(retriever: HybridRetriever, items: list[dict[str, Any]], mode: str = "bm25") -> dict[str, Any]:
    prec: dict[int, list[float]] = {k: [] for k in KS}
    rec: dict[int, list[float]] = {k: [] for k in KS}
    mrr: list[float] = []
    ndcg: list[float] = []
    misses: list[dict[str, Any]] = []
    for q in items:
        if not q["answerable"]:
            continue
        res = retriever.search(SearchRequest(query=q["question"], top_k=10, mode=mode))  # type: ignore[arg-type]
        keys = [h.chunk.chunk_key for h in res.hits]
        gold = set(q["gold_chunks"])
        for k in KS:
            hit = len(gold & set(keys[:k]))
            prec[k].append(hit / k)
            rec[k].append(hit / len(gold))
        first = next((i for i, c in enumerate(keys, 1) if c in gold), None)
        mrr.append(1 / first if first else 0.0)
        dcg = sum(1 / math.log2(i + 2) for i, c in enumerate(keys[:10]) if c in gold)
        ideal = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
        ndcg.append(dcg / ideal)
        if not gold <= set(keys[:5]):
            misses.append({"id": q["id"], "gold": sorted(gold), "top5": keys[:5]})
    return {
        "n": len(mrr),
        "precision": {f"@{k}": _mean(v) for k, v in prec.items()},
        "recall": {f"@{k}": _mean(v) for k, v in rec.items()},
        "mrr": _mean(mrr),
        "ndcg@10": _mean(ndcg),
        "not_all_gold_in_top5": misses,
    }


def _grounded(resp: Any, tool_text: str) -> tuple[int, int]:
    """(grounded claims, claims) recomputed from the response and the retriever's chunks."""
    ok = 0
    for cl in resp.claims:
        quotes = " ".join(c.quote for c in cl.citations)
        nums_ok = numbers(cl.text) <= numbers(quotes + " " + tool_text)
        cites_ok = bool(cl.citations) or bool(cl.tool_result_ids)
        ok += int(nums_ok and cites_ok)
    return ok, len(resp.claims)


def copilot(cop: ScientificCopilot, items: list[dict[str, Any]], mode: str = "bm25") -> dict[str, Any]:
    by_chunk = {c.chunk_id: c for c in cop.retriever.chunks}
    rows: list[dict[str, Any]] = []
    for q in items:
        r = cop.ask(CopilotRequest(question=q["question"], mode=mode))  # type: ignore[arg-type]
        cited = [c for cl in r.claims for c in cl.citations]
        keys = [c.chunk_key for c in cited]
        gold = set(q.get("gold_chunks") or [])
        tool_text = " ".join(json.dumps(t.result, default=str) for t in r.tool_results if t.ok and t.result)
        g_ok, g_n = _grounded(r, tool_text)
        verbatim = all(
            c.chunk_id in by_chunk
            and _ws(c.quote) in _ws(by_chunk[c.chunk_id].text)
            and c.chunk_id in r.retrieved_chunk_ids
            for c in cited
        )
        rows.append(
            {
                "id": q["id"],
                "split": q["split"],
                "category": q["category"],
                "expected": q["expected_status"],
                "got": r.status.value,
                "reason": r.abstention_reason,
                "status_ok": r.status.value == q["expected_status"]
                or (q["expected_status"] == "answered" and r.status.value == "answered_with_ambiguity"),
                "refused": r.status.value in REFUSED,
                "should_refuse": q["expected_status"] in REFUSED,
                "cited": keys,
                "gold": sorted(gold),
                "citation_gold": sum(k in gold for k in keys),
                "citations": len(keys),
                "gold_cited": len(gold & set(keys)),
                "n_gold": len(gold),
                "answer_support": bool(q.get("gold_quote"))
                and _ws(str(q.get("gold_quote"))) in _ws(r.answer),
                "grounded": g_ok,
                "claims": g_n,
                "verbatim": verbatim,
                "ineligible": sum(
                    not by_chunk[c.chunk_id].usable_as_evidence for c in cited if c.chunk_id in by_chunk
                ),
            }
        )
    return summarise(rows)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ans = [x for x in rows if not x["should_refuse"]]
    answered = [x for x in ans if not x["refused"]]
    tp = sum(x["refused"] and x["should_refuse"] for x in rows)
    fp = sum(x["refused"] and not x["should_refuse"] for x in rows)
    fn = sum(not x["refused"] and x["should_refuse"] for x in rows)
    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * rc / (p + rc) if p and rc else None
    cats: dict[str, list[bool]] = {}
    for x in rows:
        cats.setdefault(x["category"], []).append(x["status_ok"])
    comps = [x for x in answered if x["category"] == "comparison"]
    return {
        "n": len(rows),
        "status_accuracy": _mean([float(x["status_ok"]) for x in rows]),
        "status_accuracy_by_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(cats.items())},
        "abstention": {
            "precision": p and round(p, 4),
            "recall": rc and round(rc, 4),
            "f1": f1 and round(f1, 4),
            "false_abstentions": fp,
            "missed_abstentions": fn,
        },
        "citation_precision": _mean(
            [x["citation_gold"] / x["citations"] for x in answered if x["citations"]]
        ),
        "citation_recall": _mean([x["gold_cited"] / x["n_gold"] for x in answered if x["n_gold"]]),
        "answer_support": _mean([float(x["answer_support"]) for x in answered]),
        "comparison_completeness": _mean([float(x["gold_cited"] == x["n_gold"]) for x in comps]),
        "grounding": _mean([x["grounded"] / x["claims"] for x in rows if x["claims"]]),
        "verbatim_citations": _mean([float(x["verbatim"]) for x in rows if x["citations"]]),
        "ineligible_citations": sum(x["ineligible"] for x in rows),
        "failures": [
            {k: x[k] for k in ("id", "category", "expected", "got", "reason", "gold", "cited")}
            for x in rows
            if not x["status_ok"] or (not x["refused"] and x["n_gold"] and x["gold_cited"] < x["n_gold"])
        ],
    }


def benchmark(
    retriever: HybridRetriever, cop: ScientificCopilot, items: list[dict[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sp in ("dev", "test", "all"):
        qs = items if sp == "all" else [q for q in items if q["split"] == sp]
        out[sp] = {"retrieval": retrieval(retriever, qs), "copilot": copilot(cop, qs)}
    return out
