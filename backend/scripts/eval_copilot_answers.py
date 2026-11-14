"""Answer-level Copilot evaluation on backend/eval/copilot_answers_v4.jsonl.

    python scripts/eval_copilot_answers.py --split diagnostic --label baseline
Writes reports/copilot_eval/answers_v4_<split>_<label>.json (summary + every answer and claim as evidence).
The holdout split is meant to be run once, after fixes chosen on the diagnostic split.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.answer_eval import evaluate_item, summarise  # noqa: E402
from app.rag.config import RagConfig  # noqa: E402
from app.rag.copilot import ScientificCopilot  # noqa: E402
from app.rag.evaluation import load_questions, verify_gold  # noqa: E402
from app.rag.ingest import build_corpus  # noqa: E402
from app.rag.llm import ExtractiveProvider  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["diagnostic", "holdout", "all"], required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args(argv)
    chunks = build_corpus(ROOT)
    items = load_questions(ROOT / "backend/eval/copilot_answers_v4.jsonl")
    problems = verify_gold(items, chunks)
    if problems:
        print("\n".join(problems))
        return 2
    if args.split != "all":
        items = [q for q in items if q["split"] == args.split]
    cop = ScientificCopilot(HybridRetriever(chunks, RagConfig.from_env()), ExtractiveProvider())
    rows = [evaluate_item(cop, q) for q in items]
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT)
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "backend/app"], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()
    )
    payload = {
        "dataset": "backend/eval/copilot_answers_v4.jsonl",
        "split": args.split,
        "label": args.label,
        "code_revision": rev.stdout.strip() + (" + uncommitted backend/app changes" if dirty else ""),
        "provider": "extractive (deterministic; no LLM)",
        "retrieval_mode": "bm25",
        "summary": summarise(rows),
        "items": rows,
    }
    out = ROOT / "reports/copilot_eval"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"answers_v4_{args.split}_{args.label}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    s = payload["summary"]
    print(json.dumps({k: v for k, v in s.items() if k != "failures"}, indent=1))
    print(f"failures: {len(s['failures'])} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
