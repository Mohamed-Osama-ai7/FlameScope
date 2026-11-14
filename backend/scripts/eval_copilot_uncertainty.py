"""Uncertainty-aware evaluation on backend/eval/copilot_uncertainty_v5.jsonl.

    python scripts/eval_copilot_uncertainty.py --split diagnostic --label baseline
Writes reports/copilot_eval/uncertainty_v5_<split>_<label>.json. Holdout is run once, after fixes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.config import RagConfig  # noqa: E402
from app.rag.copilot import ScientificCopilot  # noqa: E402
from app.rag.evaluation import load_questions, verify_gold  # noqa: E402
from app.rag.ingest import build_corpus  # noqa: E402
from app.rag.llm import ExtractiveProvider  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402
from app.rag.uncertainty_eval import evaluate_item, summarise  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["diagnostic", "holdout", "all"], required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args(argv)
    chunks = build_corpus(ROOT)
    items = load_questions(ROOT / "backend/eval/copilot_uncertainty_v5.jsonl")
    if problems := verify_gold(items, chunks):
        print("\n".join(problems))
        return 2
    items = items if args.split == "all" else [q for q in items if q["split"] == args.split]
    cop = ScientificCopilot(HybridRetriever(chunks, RagConfig.from_env()), ExtractiveProvider())
    rows = [evaluate_item(cop, q) for q in items]
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT)
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "backend/app"], capture_output=True, text=True, cwd=ROOT
    )
    payload = {
        "dataset": "backend/eval/copilot_uncertainty_v5.jsonl",
        "split": args.split,
        "label": args.label,
        "code_revision": rev.stdout.strip()
        + (" + uncommitted backend/app changes" if dirty.stdout.strip() else ""),
        "provider": "extractive (deterministic; no LLM)",
        "summary": summarise(rows),
        "items": rows,
    }
    out = ROOT / "reports/copilot_eval"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"uncertainty_v5_{args.split}_{args.label}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    s = payload["summary"]
    print(json.dumps({k: v for k, v in s.items() if k != "failures"}, indent=1))
    print(f"failures: {len(s['failures'])} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
