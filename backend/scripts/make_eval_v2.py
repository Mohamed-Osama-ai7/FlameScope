"""Derive backend/eval/rag_questions_v2.jsonl from v1 (v1 is kept unchanged for the historical results).

Changes, all mechanical and recorded per question in `v2_change`:
* gold in PSI-25 (ACQUIRED_BUT_EXCLUDED) -> answerable=false, category excluded_source
* gold in NASA/TP-2015-216046 captions (UNREGISTERED) -> answerable=false, category unregistered_source
* gold in PSI-69 rows -> gold_quote rewritten to the chunker-1.1.0 statement of the same cell
No question text, id or split changes. Run from backend/: python scripts/make_eval_v2.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/eval/rag_questions_v1.jsonl"
DST = ROOT / "backend/eval/rag_questions_v2.jsonl"

# Former caption questions whose answer is ALSO a PSI-69 table column (eligible evidence). Found when the
# v2 run answered them from the row; relabelled with the row as gold (recorded per question).
REANSWERABLE = {
    "Q41": ("PSI-69:row:100", "FLEX-100 ambient pressure: 536.7 mmHg"),
}

ROW_QUOTES = {  # v1 quote (chunker-1.0.0) -> statement of the same source cell in chunker-1.1.0
    "Q23": "FLEX-001 reported burning-rate constant K: 0.52 mm^2/s",
    "Q25": "FLEX-002 initial droplet diameter: 1.86 mm",
    "Q26": "FLEX-001 burn time: 4.3 s",
    "Q27": "test end Disruption.",
    "Q28": "FLEX-070 ambient pressure: 761 mmHg",
    "Q29": "identifier 193F001",
    "Q31": "FLEX-073 reported burning-rate constant K: 0.56 mm^2/s",
    "Q32": "FLEX-130 reported burning-rate constant K: 0.05 mm^2/s, QUALIFIED",
}


def main() -> None:
    out = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        gold = q.get("gold_chunks") or []
        if q["answerable"] and any(g.startswith("PSI-25:") for g in gold):
            q.update(
                answerable=False,
                expected_status="abstained",
                v1_category=q.get("category"),
                category="excluded_source",
                v2_change="gold source PSI-25 is ACQUIRED_BUT_EXCLUDED; correct behaviour is to abstain",
            )
        elif q["id"] in REANSWERABLE:
            chunk, quote = REANSWERABLE[q["id"]]
            q.update(
                v1_gold_chunks=gold,
                v1_gold_quote=q["gold_quote"],
                gold_chunks=[chunk],
                gold_quote=quote,
                v2_change="v1 gold was a NASA/TP caption; the same facts are PSI-69 table columns, so the "
                "question stays answerable from eligible evidence",
            )
        elif q["answerable"] and any(g.startswith("NASA-TP-2015-216046:") for g in gold):
            q.update(
                answerable=False,
                expected_status="abstained",
                v1_category=q.get("category"),
                category="unregistered_source",
                v2_change="gold source NASA/TP-2015-216046 is UNREGISTERED; correct behaviour is to abstain",
            )
        elif q["id"] in ROW_QUOTES:
            q["v1_gold_quote"] = q["gold_quote"]
            q["gold_quote"] = ROW_QUOTES[q["id"]]
            q["v2_change"] = "gold quote rewritten for chunker-1.1.0 (same cell)"
        out.append(q)
    DST.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in out), encoding="utf-8")
    print(f"wrote {DST} ({len(out)} questions, {sum(q['answerable'] for q in out)} answerable)")


if __name__ == "__main__":
    main()
