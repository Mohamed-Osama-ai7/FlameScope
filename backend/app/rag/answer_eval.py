"""Answer-level evaluation of the Copilot (claims, not retrieval); data: eval/copilot_answers_v4.jsonl.

Deterministic checks per item:
* status_ok: answered (or answered_with_ambiguity) / abstained / comparison_blocked as expected.
* factual_correct (items with `facts`): every gold source statement (run, variable, value + unit or status
  marker) appears verbatim in the answer. The Copilot states measurements verbatim, so a missing fact means
  the requested value was not given; a wrong run's value shows up as an off-target claim.
* claim support: a claim is supported when it has at least one citation, every quote is a verbatim span of a
  usable chunk that was retrieved, and every number in the claim occurs in its quotes or a tool result.
* off-target claims (answerable items): claims whose citations include no gold chunk.
* ineligible citations: citations of chunks whose source is not usable evidence.
Narrative claims are exported for an independent review (labels stored separately; see docs/19).
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from app.rag.citations import numbers
from app.rag.copilot import CopilotRequest, ScientificCopilot

REFUSED = {"abstained", "comparison_blocked"}


def _ws(s: str) -> str:
    return " ".join(s.split())


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def evaluate_item(cop: ScientificCopilot, q: dict[str, Any]) -> dict[str, Any]:
    r = cop.ask(CopilotRequest(question=q["question"]))
    chunks = {c.chunk_id: c for c in cop.retriever.chunks}
    retrieved = set(r.retrieved_chunk_ids)
    tool_text = " ".join(json.dumps(t.result, default=str) for t in r.tool_results if t.ok and t.result)
    gold = set(q.get("gold_chunks") or [])
    claims = []
    for cl in r.claims:
        quotes = " ".join(c.quote for c in cl.citations)
        verbatim = all(
            c.chunk_id in chunks
            and c.chunk_id in retrieved
            and chunks[c.chunk_id].usable_as_evidence
            and _ws(c.quote) in _ws(chunks[c.chunk_id].text)
            for c in cl.citations
        )
        nums = numbers(cl.text) <= numbers(quotes + " " + tool_text)
        claims.append(
            {
                "text": cl.text,
                "cited": [c.chunk_key for c in cl.citations],
                "supported": bool(cl.citations or cl.tool_result_ids) and verbatim and nums,
                "on_gold": bool(gold & {c.chunk_key for c in cl.citations}),
                "measurement_status": cl.measurement_status,
                "ineligible": sum(
                    not chunks[c.chunk_id].usable_as_evidence for c in cl.citations if c.chunk_id in chunks
                ),
            }
        )
    expected = q["expected_status"]
    status_ok = r.status.value == expected or (
        expected == "answered" and r.status.value == "answered_with_ambiguity"
    )
    facts = q.get("facts") or []
    return {
        "id": q["id"],
        "split": q["split"],
        "category": q["category"],
        "question": q["question"],
        "expected": expected,
        "got": r.status.value,
        "status_ok": status_ok,
        "abstention_reason": r.abstention_reason,
        "refused": r.status.value in REFUSED,
        "should_refuse": expected in REFUSED,
        "facts": facts,
        "facts_found": [f for f in facts if _ws(f) in _ws(r.answer)],
        "factual_correct": (
            all(_ws(f) in _ws(r.answer) for f in facts) if facts and r.status.value not in REFUSED else None
        ),
        "gold_quote": q.get("gold_quote") if not facts else None,
        "gold_quote_in_answer": (_ws(q["gold_quote"]) in _ws(r.answer))
        if q.get("gold_quote") and not facts
        else None,
        "claims": claims,
        "answer": r.answer,
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(x["refused"] and x["should_refuse"] for x in rows)
    fp = sum(x["refused"] and not x["should_refuse"] for x in rows)
    fn = sum(not x["refused"] and x["should_refuse"] for x in rows)
    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    all_claims = [c for x in rows for c in x["claims"]]
    answered = [x for x in rows if not x["should_refuse"] and not x["refused"]]
    ans_claims = [c for x in answered for c in x["claims"]]
    fact_items = [x for x in rows if x["facts"]]
    cats: dict[str, list[bool]] = {}
    for x in rows:
        cats.setdefault(x["category"], []).append(x["status_ok"])
    return {
        "n": len(rows),
        "status_accuracy": _mean([float(x["status_ok"]) for x in rows]),
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(cats.items())},
        "abstention": {
            "precision": p and round(p, 4),
            "recall": rc and round(rc, 4),
            "f1": round(2 * p * rc / (p + rc), 4) if p and rc else None,
            "false_abstentions": fp,
            "missed_abstentions": fn,
        },
        # factual accuracy over ALL items with facts (a refusal counts as not correct)
        "factual_accuracy": _mean([float(bool(x["factual_correct"])) for x in fact_items]),
        "claims": len(all_claims),
        "claim_support_rate": _mean([float(c["supported"]) for c in all_claims]),
        "unsupported_claims": sum(not c["supported"] for c in all_claims),
        "off_target_claims": sum(not c["on_gold"] for c in ans_claims),
        "off_target_rate": _mean([float(not c["on_gold"]) for c in ans_claims]),
        "ineligible_citations": sum(c["ineligible"] for c in all_claims),
        "failures": [
            {
                "id": x["id"],
                "category": x["category"],
                "question": x["question"],
                "expected": x["expected"],
                "got": x["got"],
                "reason": x["abstention_reason"],
                "missing_facts": sorted(set(x["facts"]) - set(x["facts_found"])),
                "off_target": [
                    c["text"][:160] for c in x["claims"] if not c["on_gold"] and not x["should_refuse"]
                ],
            }
            for x in rows
            if not x["status_ok"]
            or x["factual_correct"] is False
            or any(not c["supported"] for c in x["claims"])
            or (not x["should_refuse"] and any(not c["on_gold"] for c in x["claims"]))
        ],
    }
