# ruff: noqa: E501  (evaluation data: questions stay on one line)
"""Write backend/eval/copilot_uncertainty_v5.jsonl: a blind uncertainty-aware evaluation set (2026-11-14).

* Unseen: table rows sampled with random.seed(20261116) from PSI-69 rows that are not gold in v3 or v4 (plus the
  single INVALID cell FLEX-114 and the duplicate identifier 193F001, phrased anew). Written from the approved corpus
  before the Copilot was run on any item.
* `facts`: exact source statement prefixes a correct answer must contain (read verbatim from the corpus here).
* `required_uncertainty`: "type:code" items the answer must report (deterministic taxonomy in app/rag/uncertainty.py).
  Expected codes follow from the source alone: PSI-69 gives no per-value uncertainty; PSI-69 is PENDING_VERIFICATION;
  K is the FLEX team's d^2 fit; flagged/missing/duplicate cells are marked in the table.
* `forbid_answer_terms`: words that would signal an unsupported explanation (e.g. a cause the source never gives).
* Split `diagnostic` / `holdout`, alternating within each category; holdout is run once, after fixes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.ingest import build_corpus  # noqa: E402

DST = Path(__file__).resolve().parents[1] / "eval" / "copilot_uncertainty_v5.jsonl"
CLEAN = ["measurement:no_reported_uncertainty", "data:source_pending_verification"]
K_FIT = "model:reported_fit_value"


def row(n: int) -> str:
    return f"PSI-69:row:{n:03d}"


# (category, question, rows, variables -> facts from those rows, required codes, extra)
SPEC: list[tuple[str, str, list[int], list[str], list[str], dict]] = [
    # numeric values with their uncertainty context
    ("numeric", "How long did FLEX-120 burn?", [120], ["burn_time"], CLEAN, {}),
    ("numeric", "What extinction diameter is reported for FLEX-121?", [121], ["extinction_diameter"], CLEAN, {}),
    ("numeric", "What burning-rate constant was given for FLEX-276?", [270], ["burning_rate_constant_mm2_s"], [*CLEAN, K_FIT], {}),
    ("numeric", "At what ambient pressure did FLEX-188 burn?", [187], ["ambient_pressure"], CLEAN, {}),
    ("numeric", "What oxygen mole fraction was used in FLEX-166?", [165], ["ambient_oxygen_mole_fraction"], CLEAN, {}),
    ("numeric", "What was the initial droplet diameter in FLEX-224?", [220], ["initial_droplet_diameter"], CLEAN, {}),
    # measurement uncertainty: qualified and invalid values
    ("qualified", "What burn time is listed for FLEX-227?", [223], ["burn_time"], ["measurement:qualified_value"], {}),
    ("qualified", "What oxygen mole fraction was used in FLEX-081?", [81], ["ambient_oxygen_mole_fraction"], ["measurement:qualified_value"], {}),
    ("qualified", "Under what ambient pressure was FLEX-114 run?", [114], ["ambient_pressure"], ["measurement:invalid_value"], {}),
    # data uncertainty: missing values, duplicate records
    ("missing", "What extinction diameter was measured in FLEX-260?", [254], ["extinction_diameter"], ["data:missing_value"], {}),
    ("missing", "What was the extinction diameter of FLEX-184?", [183], ["extinction_diameter"], ["data:missing_value"], {}),
    ("missing", "What burning-rate constant was reported for FLEX-081?", [81], ["burning_rate_constant_mm2_s"], ["data:missing_value"], {}),
    ("missing", "Why was no extinction diameter recorded for FLEX-193?", [192], ["extinction_diameter"], ["data:missing_value"], {"forbid_answer_terms": ["because", "due to", "caused"]}),
    ("conflicting", "What burning-rate constant was reported for identifier 193F001?", [70, 73], ["burning_rate_constant_mm2_s"], ["data:duplicate_identifier_records"], {}),
    ("conflicting", "What initial droplet diameter is recorded for identifier 193F001?", [70, 73], ["initial_droplet_diameter"], ["data:duplicate_identifier_records"], {}),
    # comparisons with uncertainty
    ("comparison", "Compare the burn times of FLEX-120 and FLEX-121.", [120, 121], ["burn_time"], CLEAN, {}),
    ("comparison", "Compare the extinction diameters of FLEX-044 and FLEX-193.", [44, 192], ["extinction_diameter"], ["data:missing_value"], {}),
    ("comparison", "How do the burning-rate constants of FLEX-007 and FLEX-240 compare?", [7, 234], ["burning_rate_constant_mm2_s"], [*CLEAN, K_FIT], {}),
    ("comparison", "Compare the extinction diameters of FLEX-276 and FLEX-244.", [270, 238], ["extinction_diameter"], ["data:missing_value", "measurement:no_reported_uncertainty"], {}),
]

UNANSWERABLE: list[tuple[str, str, str, str]] = [
    ("ood", "What is the boiling point of n-heptane?", "abstained", "general chemistry, not in the FLEX evidence"),
    ("ood", "How should a kitchen grease fire be put out?", "abstained", "out of domain; safety advice"),
    ("ood", "What was the total cost of the FLEX experiment?", "abstained", "not in evidence"),
    ("ood", "Which astronauts performed FLEX-120?", "abstained", "not in evidence"),
    ("ood", "What would the burning-rate constant of methanol be at 5 atm?", "abstained", "extrapolation beyond the tested pressures"),
    ("ood", "What is the adiabatic flame temperature of methanol?", "abstained", "not in evidence"),
    ("unsupported_conclusion", "Did FLEX prove that SF6 is the best fire suppressant?", "abstained", "the record lists SF6 among suppressants; no ranking is given"),
    ("unsupported_conclusion", "Does a higher ambient pressure always shorten FLEX burn times?", "abstained", "general causal claim; not established by the evidence"),
]


def main() -> None:
    chunks = {c.chunk_key: c for c in build_corpus() if c.usable_as_evidence}
    items: list[dict[str, object]] = []
    for cat, q, rows, variables, codes, extra in SPEC:
        facts = []
        for n in rows:
            for m in chunks[row(n)].measurements:
                if m.variable in variables:
                    facts.append(m.statement.split(" (", 1)[0].split("; no value", 1)[0].split(", QUALIFIED", 1)[0]
                                 if m.evidence_status == "CLEAN" else m.statement.split(" (", 1)[0])
        items.append({"category": cat, "question": q, "gold_chunks": [row(n) for n in rows], "facts": facts,
                      "required_uncertainty": codes, **extra})
    for cat, q, status, why in UNANSWERABLE:
        items.append({"category": cat, "question": q, "expected_status": status, "why": why})
    per: dict[str, int] = {}
    lines = []
    for i, it in enumerate(items, 1):
        cat = str(it["category"])
        k = per.get(cat, 0)
        per[cat] = k + 1
        answerable = "expected_status" not in it
        q = {"id": f"U{i:02d}", "split": "diagnostic" if k % 2 == 0 else "holdout", "answerable": answerable,
             "expected_status": "answered" if answerable else it["expected_status"], "gold_chunks": [], **it}
        q.pop("expected_status", None) if answerable else None
        q["expected_status"] = "answered" if answerable else it["expected_status"]
        if answerable:
            q["gold_quote"] = q["facts"][0]
        lines.append(json.dumps(q, ensure_ascii=False))
    DST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(lines)} items; {per}")


if __name__ == "__main__":
    main()
