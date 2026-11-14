# ruff: noqa: E501  (evaluation data: questions and verbatim gold statements stay on one line)
"""Write backend/eval/copilot_answers_v4.jsonl: a blind answer-level evaluation set (2026-11-14).

* Separate from v1-v3: table rows sampled with random.seed(20261115) from PSI-69 rows not used in v3; narrative
  chunks not used as v3 gold. Written from the approved corpus text before the Copilot was run on any item.
* Numeric items carry `facts`: the exact source statement prefix (run, variable, value, unit or status marker)
  that a correct answer must contain. Narrative items carry a verbatim gold quote and get an independent review.
* Split: `diagnostic` (may be inspected to choose fixes) and `holdout` (run once, after fixes), alternating within
  each category.
"""

from __future__ import annotations

import json
from pathlib import Path

DST = Path(__file__).resolve().parents[1] / "eval" / "copilot_answers_v4.jsonl"


def row(n: int) -> str:
    return f"PSI-69:row:{n:03d}"


ITEMS: list[dict[str, object]] = [
    # ---- numeric, paraphrased (one measurement) ----
    {
        "category": "numeric",
        "question": "How long did the flame last in FLEX-161?",
        "gold_chunks": [row(160)],
        "facts": ["FLEX-161 burn time: 14.8 s"],
    },
    {
        "category": "numeric",
        "question": "What oxygen fraction surrounded the droplet in FLEX-258?",
        "gold_chunks": [row(252)],
        "facts": ["FLEX-258 O2 mole fraction: 0.24 mole fraction"],
    },
    {
        "category": "numeric",
        "question": "How big was the droplet when its flame went out in FLEX-086?",
        "gold_chunks": [row(86)],
        "facts": ["FLEX-086 visible flame extinction diameter: 2.56 mm"],
    },
    {
        "category": "numeric",
        "question": "What burning-rate constant was reported for FLEX-187?",
        "gold_chunks": [row(186)],
        "facts": ["FLEX-187 reported burning-rate constant K: 0.52 mm^2/s"],
    },
    {
        "category": "numeric",
        "question": "What was the initial diameter of the FLEX-094 droplet?",
        "gold_chunks": [row(94)],
        "facts": ["FLEX-094 initial droplet diameter: 3.53 mm"],
    },
    {
        "category": "numeric",
        "question": "Under what pressure did FLEX-245 burn?",
        "gold_chunks": [row(239)],
        "facts": ["FLEX-245 ambient pressure: 754.2 mmHg"],
    },
    {
        "category": "numeric",
        "question": "What extinction diameter is reported for FLEX-102?",
        "gold_chunks": [row(102)],
        "facts": ["FLEX-102 visible flame extinction diameter: 3.43 mm"],
    },
    {
        "category": "numeric",
        "question": "What oxygen mole fraction was used in FLEX-025?",
        "gold_chunks": [row(25)],
        "facts": ["FLEX-025 O2 mole fraction: 0.3 mole fraction"],
    },
    {
        "category": "numeric",
        "question": "How many seconds did FLEX-099 burn?",
        "gold_chunks": [row(99)],
        "facts": ["FLEX-099 burn time: 33 s"],
    },
    {
        "category": "numeric",
        "question": "What value of K did the FLEX team give for FLEX-043?",
        "gold_chunks": [row(43)],
        "facts": ["FLEX-043 reported burning-rate constant K: 0.78 mm^2/s"],
    },
    # ---- flagged or missing values: the answer must state the status, never a clean number ----
    {
        "category": "flagged",
        "question": "What extinction diameter was recorded for FLEX-051?",
        "gold_chunks": [row(51)],
        "facts": ["FLEX-051 visible flame extinction diameter: 0 mm, QUALIFIED"],
    },
    {
        "category": "flagged",
        "question": "What extinction diameter was measured in FLEX-128?",
        "gold_chunks": [row(128)],
        "facts": ["FLEX-128 visible flame extinction diameter: MISSING in the source"],
    },
    {
        "category": "flagged",
        "question": "What burning-rate constant was reported for FLEX-014?",
        "gold_chunks": [row(14)],
        "facts": ["FLEX-014 reported burning-rate constant K: MISSING in the source"],
    },
    {
        "category": "flagged",
        "question": "What was the initial droplet diameter in FLEX-080?",
        "gold_chunks": [row(80)],
        "facts": ["FLEX-080 initial droplet diameter: MISSING in the source"],
    },
    # ---- comparisons between two FLEX runs: both values must be stated ----
    {
        "category": "comparison",
        "question": "Compare the burn times of FLEX-161 and FLEX-099.",
        "gold_chunks": [row(160), row(99)],
        "facts": ["FLEX-161 burn time: 14.8 s", "FLEX-099 burn time: 33 s"],
    },
    {
        "category": "comparison",
        "question": "Which had the larger initial droplet diameter, FLEX-094 or FLEX-102?",
        "gold_chunks": [row(94), row(102)],
        "facts": ["FLEX-094 initial droplet diameter: 3.53 mm", "FLEX-102 initial droplet diameter: 3.57 mm"],
    },
    {
        "category": "comparison",
        "question": "How do the reported burning-rate constants of FLEX-187 and FLEX-043 compare?",
        "gold_chunks": [row(186), row(43)],
        "facts": [
            "FLEX-187 reported burning-rate constant K: 0.52 mm^2/s",
            "FLEX-043 reported burning-rate constant K: 0.78 mm^2/s",
        ],
    },
    {
        "category": "comparison",
        "question": "Was the ambient pressure of FLEX-258 different from that of FLEX-086?",
        "gold_chunks": [row(252), row(86)],
        "facts": ["FLEX-258 ambient pressure: 534.6 mmHg", "FLEX-086 ambient pressure: 770 mmHg"],
    },
    # ---- scientific narrative (verbatim gold quote + independent review) ----
    {
        "category": "scientific",
        "question": "On which hardware were the FLEX experiments run?",
        "gold_chunks": ["PSI-69:meta:summary"],
        "gold_quote": "Multi-user Droplet Combustion Appartatus (MDCA)",
    },
    {
        "category": "scientific",
        "question": "What did FLEX do when a finite extinction diameter was observed?",
        "gold_chunks": ["PSI-69:meta:approach:02"],
        "gold_quote": "Increase the droplet size or repeat the test",
    },
    {
        "category": "scientific",
        "question": "How was the LOI determined when extinction droplets were too small to observe?",
        "gold_chunks": ["PSI-69:meta:approach:03", "PSI-69:meta:approach:04"],
        "gold_quote": "burn to completion followed by a no ignition test",
    },
    {
        "category": "scientific",
        "question": "How was a slow convective flow applied to FLEX droplets near the end of a test?",
        "gold_chunks": ["PSI-69:meta:approach:05"],
        "gold_quote": "imparted by translating the droplet at a slow, uniform speed",
    },
    {
        "category": "scientific",
        "question": "How does FLEX contribute to crew safety on future space missions?",
        "gold_chunks": ["PSI-69:meta:researchImpacts:01"],
        "gold_quote": "improved fire safety protocols for future space missions",
    },
    {
        "category": "scientific",
        "question": "Which NASA centre managed the FLEX investigation?",
        "gold_chunks": ["PSI-69:meta:summary"],
        "gold_quote": "Managing centre: Glenn Research Center (GRC)",
    },
    # ---- unanswerable: must abstain or block ----
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "What was the soot temperature in FLEX-187?",
        "why": "not in evidence",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "What was the flame standoff ratio of FLEX-094?",
        "why": "not in evidence",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "What is the extinction diameter of FLEX test 500?",
        "why": "nonexistent test",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "Predict the burn time of a 10 mm heptane droplet in FLEX conditions.",
        "why": "extrapolation",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "What was the flame spread rate measured in BASS-II?",
        "why": "PSI-25 ACQUIRED_BUT_EXCLUDED",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "How large was the sample burned in SAFFIRE-I?",
        "why": "PSI-98 QUARANTINED",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "What does NASA/TP-2015-216046 say about cool flames in FLEX-100?",
        "why": "NASA/TP unregistered",
    },
    {
        "category": "unanswerable",
        "expected_status": "comparison_blocked",
        "question": "Compare the FLEX-025 burning rate with the flame spread in SAFFIRE.",
        "why": "cross-regime",
    },
    {
        "category": "unanswerable",
        "expected_status": "comparison_blocked",
        "question": "Is methanol droplet burning in FLEX faster than PMMA burning in BASS-II?",
        "why": "cross-regime",
    },
    {
        "category": "unanswerable",
        "expected_status": "abstained",
        "question": "Which FLEX test used a propanol droplet?",
        "why": "no propanol runs in PSI-69",
    },
]


def main() -> None:
    per: dict[str, int] = {}
    lines = []
    for i, it in enumerate(ITEMS, 1):
        cat = str(it["category"])
        k = per.get(cat, 0)
        per[cat] = k + 1
        answerable = "expected_status" not in it
        q = {
            "id": f"A{i:02d}",
            "split": "diagnostic" if k % 2 == 0 else "holdout",
            "answerable": answerable,
            "expected_status": "answered" if answerable else it["expected_status"],
            "gold_chunks": [],
            **{key: v for key, v in it.items() if key != "expected_status"},
        }
        if "facts" in q and "gold_quote" not in q:
            q["gold_quote"] = q["facts"][0]  # verify_gold checks it as a verbatim span of a gold chunk
        lines.append(json.dumps(q, ensure_ascii=False))
    DST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(lines)} items; {per}")


if __name__ == "__main__":
    main()
