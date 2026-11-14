"""Evaluation of uncertainty-aware answering on backend/eval/copilot_uncertainty_v5.jsonl (deterministic).

Per item: status (answered / abstained / comparison_blocked); factual correctness (gold source
statements verbatim in the answer); required uncertainty codes present; every uncertainty item is
supported (each evidence id is a measurement cited in the answer, a retrieved chunk, or a source named in
source_eligibility; items without ids must come from the abstention reason or the answer's own
missing/withheld lists); no forbidden terms (e.g. an unsupported cause); no contradictory codes (a clean
value labelled qualified/invalid/missing).

Selective prediction: coverage = answered answerable / answerable; selective accuracy = factually correct /
answered answerable; risk on unanswerable = answered / unanswerable. Probability calibration is NOT computed:
the Copilot emits no probabilities and no confidence score is derived from a model.
"""

from __future__ import annotations

import statistics
from typing import Any

from app.rag.copilot import CopilotRequest, ScientificCopilot

REFUSED = {"abstained", "comparison_blocked"}
CONTRADICTORY_FOR_CLEAN = {"measurement:qualified_value", "measurement:invalid_value", "data:missing_value"}


def _ws(s: str) -> str:
    return " ".join(s.split())


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def evaluate_item(cop: ScientificCopilot, q: dict[str, Any]) -> dict[str, Any]:
    r = cop.ask(CopilotRequest(question=q["question"]))
    measured = {m.measurement_id for cl in r.claims for c in cl.citations for m in c.measurements}
    retrieved = set(r.retrieved_chunk_ids)
    sources = set(r.source_eligibility)
    unsupported: list[str] = []
    for u in r.uncertainty:
        ok_ids = all(e in measured or e in retrieved or e in sources for e in u.evidence)
        if not u.evidence:
            ok_ids = u.kind == "retrieval" or u.code in {
                "pooling_refused",
                "absent_fuel",
                "incompatible_regimes",
                "claims_failed_validation",
                "provider_unavailable",
            }
        if not ok_ids:
            unsupported.append(u.key)
    produced = {u.key for u in r.uncertainty}
    required = set(q.get("required_uncertainty") or [])
    expected = q["expected_status"]
    refused = r.status.value in REFUSED
    status_ok = r.status.value == expected or (
        expected == "answered" and r.status.value == "answered_with_ambiguity"
    )
    facts = q.get("facts") or []
    clean_item = bool(facts) and all(
        "MISSING" not in f and "QUALIFIED" not in f and "INVALID" not in f for f in facts
    )
    return {
        "id": q["id"],
        "split": q["split"],
        "category": q["category"],
        "question": q["question"],
        "expected": expected,
        "got": r.status.value,
        "status_ok": status_ok,
        "refused": refused,
        "should_refuse": expected in REFUSED,
        "abstention_reason": r.abstention_reason,
        "facts": facts,
        "factual_correct": (
            all(_ws(f) in _ws(r.answer) for f in facts)
            if facts and not refused
            else (False if facts else None)
        ),
        "required": sorted(required),
        "produced": sorted(produced),
        "missing_codes": sorted(required - produced),
        "unsupported_explanations": unsupported,
        "contradictory_codes": sorted(produced & CONTRADICTORY_FOR_CLEAN) if clean_item else [],
        "forbidden_terms": [t for t in q.get("forbid_answer_terms", []) if t.lower() in r.answer.lower()],
        "uncertainty": [u.model_dump() for u in r.uncertainty],
        "answer": r.answer,
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(x["refused"] and x["should_refuse"] for x in rows)
    fp = sum(x["refused"] and not x["should_refuse"] for x in rows)
    fn = sum(not x["refused"] and x["should_refuse"] for x in rows)
    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    ans = [x for x in rows if not x["should_refuse"]]
    answered = [x for x in ans if not x["refused"]]
    una = [x for x in rows if x["should_refuse"]]
    req = [(x, c) for x in ans for c in x["required"]]
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
            "false_abstentions": fp,
            "missed_abstentions": fn,
        },
        "ood_abstention_rate": _mean([float(x["refused"]) for x in rows if x["category"] == "ood"]),
        "factual_accuracy": _mean([float(bool(x["factual_correct"])) for x in ans if x["facts"]]),
        "uncertainty_code_recall": _mean([float(c not in x["missing_codes"]) for x, c in req]),
        "items_with_all_required_codes": _mean([float(not x["missing_codes"]) for x in answered]),
        "unsupported_explanations": sum(len(x["unsupported_explanations"]) for x in rows),
        "contradictory_codes": sum(len(x["contradictory_codes"]) for x in rows),
        "forbidden_terms": sum(len(x["forbidden_terms"]) for x in rows),
        "selective": {
            "coverage": _mean([float(not x["refused"]) for x in ans]),
            "selective_accuracy": _mean([float(bool(x["factual_correct"])) for x in answered if x["facts"]]),
            "risk_on_unanswerable": _mean([float(not x["refused"]) for x in una]),
        },
        "calibration": "not computed: no probabilities are produced and no model self-confidence is used",
        "failures": [
            {
                k: x[k]
                for k in (
                    "id",
                    "category",
                    "question",
                    "expected",
                    "got",
                    "abstention_reason",
                    "missing_codes",
                    "unsupported_explanations",
                    "contradictory_codes",
                    "forbidden_terms",
                )
            }
            | {"factual_correct": x["factual_correct"]}
            for x in rows
            if not x["status_ok"]
            or x["missing_codes"]
            or x["unsupported_explanations"]
            or x["contradictory_codes"]
            or x["forbidden_terms"]
            or x["factual_correct"] is False
        ],
    }
