# ruff: noqa: E501  (golden-set data: questions and verbatim gold quotes are kept on one line)
"""Write backend/eval/rag_golden_v3.jsonl: a blind golden set for the RAG + Copilot (2026-11-14).

Authoring rules (recorded so the set can be audited):
* Written from the approved corpus text only (PSI-69 record narrative and table rows; usable chunks), BEFORE the
  retriever or Copilot was run on any of these questions. Table rows were chosen with random.seed(20261114)
  from the 274 PSI-69 rows (a sample of 10, first 8 used for direct questions, pairs for comparisons).
* Every answerable item has gold chunk keys and a gold quote that verify_gold() checks as a verbatim span of a
  gold chunk that is usable evidence. Refusal items carry the expected status and why.
* Questions are paraphrased (not copied from the statements) so lexical overlap is not built in.
* Split: items alternate dev/test within each category; tuning may look at dev only.
"""

from __future__ import annotations

import json
from pathlib import Path

DST = Path(__file__).resolve().parents[1] / "eval" / "rag_golden_v3.jsonl"


def row(n: int) -> str:
    return f"PSI-69:row:{n:03d}"


ITEMS: list[dict[str, object]] = [
    # ---- direct evidence: one measurement of one run (paraphrased) ----
    {
        "category": "direct",
        "question": "How large was the droplet at ignition in FLEX-033?",
        "gold_chunks": [row(33)],
        "gold_quote": "FLEX-033 initial droplet diameter: 2.62 mm",
    },
    {
        "category": "direct",
        "question": "For how many seconds did the FLEX-124 droplet burn?",
        "gold_chunks": [row(124)],
        "gold_quote": "FLEX-124 burn time: 2.4 s",
    },
    {
        "category": "direct",
        "question": "What burning-rate constant did the FLEX team report for FLEX-254?",
        "gold_chunks": [row(248)],
        "gold_quote": "FLEX-254 reported burning-rate constant K: 0.51 mm^2/s",
    },
    {
        "category": "direct",
        "question": "At what chamber pressure was FLEX-265 run?",
        "gold_chunks": [row(259)],
        "gold_quote": "FLEX-265 ambient pressure: 529 mmHg",
    },
    {
        "category": "direct",
        "question": "What was the starting droplet diameter of test FLEX-067?",
        "gold_chunks": [row(67)],
        "gold_quote": "FLEX-067 initial droplet diameter: 3.97 mm",
    },
    {
        "category": "direct",
        "question": "Which K value is tabulated for FLEX-261?",
        "gold_chunks": [row(255)],
        "gold_quote": "FLEX-261 reported burning-rate constant K: 0.56 mm^2/s",
    },
    {
        "category": "direct",
        "question": "What ambient pressure is listed for the high-pressure test FLEX-013?",
        "gold_chunks": [row(13)],
        "gold_quote": "FLEX-013 ambient pressure: 2074.2 mmHg",
    },
    {
        "category": "direct",
        "question": "How long was the burn in FLEX-231?",
        "gold_chunks": [row(225)],
        "gold_quote": "FLEX-231 burn time: 12.5 s",
    },
    # ---- comparisons between FLEX runs (same regime; values must come from both rows, nothing computed) ----
    {
        "category": "comparison",
        "question": "Compare the burn times of FLEX-033 and FLEX-122.",
        "gold_chunks": [row(33), row(122)],
        "gold_quote": "FLEX-122 burn time: 13.9 s",
    },
    {
        "category": "comparison",
        "question": "Was the reported K of FLEX-013 higher than that of FLEX-067?",
        "gold_chunks": [row(13), row(67)],
        "gold_quote": "FLEX-013 reported burning-rate constant K: 0.49 mm^2/s",
    },
    {
        "category": "comparison",
        "question": "Which started with the larger droplet, FLEX-225 or FLEX-261?",
        "gold_chunks": [row(221), row(255)],
        "gold_quote": "FLEX-261 initial droplet diameter: 3.22 mm",
    },
    {
        "category": "comparison",
        "question": "How do the ambient pressures of FLEX-124 and FLEX-231 differ?",
        "gold_chunks": [row(124), row(225)],
        "gold_quote": "FLEX-124 ambient pressure: 532.4 mmHg",
    },
    # ---- scientific questions answered by the PSI-69 record narrative ----
    {
        "category": "scientific",
        "question": "Which gaseous suppressants does FLEX set out to test?",
        "gold_chunks": ["PSI-69:meta:objective:01"],
        "gold_quote": "such as CO2, He, and SF6",
    },
    {
        "category": "scientific",
        "question": "What does FLEX aim to determine as a function of ambient pressure?",
        "gold_chunks": ["PSI-69:meta:approach:01"],
        "gold_quote": "Limiting Oxygen Index (LOI) as a function of ambient pressure",
    },
    {
        "category": "scientific",
        "question": "According to the FLEX hypothesis, why would microgravity change droplet extinction?",
        "gold_chunks": ["PSI-69:meta:hypothesis:01"],
        "gold_quote": "due to changes in species and energy transport dynamics",
    },
    {
        "category": "scientific",
        "question": "Which flight experiment measurements does FLEX list among its key goals?",
        "gold_chunks": ["PSI-69:meta:objective:02"],
        "gold_quote": "high-resolution measurements of droplet burning rates",
    },
    {
        "category": "scientific",
        "question": "How could studying cool flames benefit engine design?",
        "gold_chunks": ["PSI-69:meta:researchImpacts:03"],
        "gold_quote": "inform the design of advanced combustion engines",
    },
    {
        "category": "scientific",
        "question": "Did most FLEX tests use free or fiber-supported droplets?",
        "gold_chunks": ["PSI-69:meta:approach:06"],
        "gold_quote": "a large number of the tests involve free droplets",
    },
    {
        "category": "scientific",
        "question": "Which publication analysed quasi-steady n-heptane droplet combustion with cool-flame chemistry?",
        "gold_chunks": ["PSI-69:meta:publications:03"],
        "gold_quote": "Asymptotic analysis of quasi-steady n-heptane droplet combustion supported by cool-flame chemistry",
    },
    {
        "category": "scientific",
        "question": "Which PSI-69 publication studied methanol droplet combustion in oxygen-inert environments?",
        "gold_chunks": ["PSI-69:meta:publications:01"],
        "gold_quote": "Methanol Droplet Combustion in Oxygen-Inert Environments in Microgravity",
    },
    # ---- cross-regime comparisons (must be blocked by the comparison gate) ----
    {
        "category": "invalid_comparison",
        "expected_status": "comparison_blocked",
        "question": "Is the FLEX-033 burning-rate constant larger than the BASS-II flame spread rate?",
        "why": "different regimes and quantities; validate_comparison forbids a shared axis",
    },
    {
        "category": "invalid_comparison",
        "expected_status": "comparison_blocked",
        "question": "Compare methanol droplet burning in FLEX with SAFFIRE large-scale fires.",
        "why": "droplet vs spacecraft-scale regime",
    },
    {
        "category": "invalid_comparison",
        "expected_status": "comparison_blocked",
        "question": "Do FLEX heptane droplets burn faster than solid PMMA samples in BASS-II?",
        "why": "liquid droplet vs solid fuel regime",
    },
    # ---- unsupported questions (answer not in the approved evidence) ----
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What flame temperature in kelvin was measured during FLEX-124?",
        "why": "no temperature in the table rows",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "Which FLEX test burned an ethanol droplet?",
        "why": "no ethanol runs in PSI-69",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What soot volume fraction was recorded in FLEX-033?",
        "why": "no soot values in the table",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What will the burning rate constant of heptane be on the Moon?",
        "why": "extrapolation",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What was the burn time of FLEX test 400?",
        "why": "nonexistent test",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What was the radiative heat loss in watts for FLEX-067?",
        "why": "quantity not in evidence",
    },
    {
        "category": "unsupported",
        "expected_status": "abstained",
        "question": "What is the average K of all methanol droplets?",
        "why": "pooling per-run values is refused; the descriptive summary tool is only offered for explicit statistics",
    },
    # ---- excluded, quarantined and unregistered sources (must never be used) ----
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "Which fuel sample was burned in BASS-II test B1?",
        "why": "PSI-25 ACQUIRED_BUT_EXCLUDED",
    },
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "What hypothesis does BASS-II test about burning in microgravity?",
        "why": "PSI-25 excluded",
    },
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "What hardware housed the Saffire-I experiment?",
        "why": "PSI-98 QUARANTINED",
    },
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "Which materials were tested in SAFFIRE?",
        "why": "PSI-98 quarantined",
    },
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "What does the NASA technical report caption say about the vapor cloud in FLEX-100?",
        "why": "NASA/TP-2015-216046 UNREGISTERED",
    },
    {
        "category": "ineligible_source",
        "expected_status": "abstained",
        "question": "According to NASA/TP-2015-216046, how was the FLEX-130 droplet supported?",
        "why": "NASA/TP-2015-216046 unregistered",
    },
]


def main() -> None:
    per_cat: dict[str, int] = {}
    lines = []
    for i, it in enumerate(ITEMS, 1):
        cat = str(it["category"])
        k = per_cat.get(cat, 0)
        per_cat[cat] = k + 1
        answerable = "expected_status" not in it
        q = {
            "id": f"G{i:02d}",
            "split": "dev" if k % 2 == 0 else "test",
            "answerable": answerable,
            "expected_status": "answered" if answerable else it["expected_status"],
            **{key: v for key, v in it.items() if key != "expected_status"},
        }
        if not answerable:
            q.setdefault("gold_chunks", [])
        lines.append(json.dumps(q, ensure_ascii=False))
    DST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(lines)} items; {per_cat}")


if __name__ == "__main__":
    main()
