"""Run the golden-set benchmark and write reports/rag_eval/benchmark_v3_<label>.json.

    python scripts/benchmark_rag.py --label baseline
Deterministic: BM25 retrieval (default), extractive provider (no LLM), fixed dataset.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.benchmark import benchmark  # noqa: E402
from app.rag.config import RagConfig  # noqa: E402
from app.rag.copilot import ScientificCopilot  # noqa: E402
from app.rag.evaluation import load_questions, verify_gold  # noqa: E402
from app.rag.ingest import build_corpus  # noqa: E402
from app.rag.llm import ExtractiveProvider  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--dataset", default="rag_golden_v3.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "rag_eval")
    args = ap.parse_args(argv)
    chunks = build_corpus(ROOT)
    items = load_questions(ROOT / "backend" / "eval" / args.dataset)
    problems = verify_gold(items, chunks)
    if problems:
        print("GOLD LABEL PROBLEMS:\n" + "\n".join(problems))
        return 2
    retriever = HybridRetriever(chunks, RagConfig.from_env())
    result = benchmark(retriever, ScientificCopilot(retriever, ExtractiveProvider()), items)
    rev = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    payload = {
        "dataset": f"backend/eval/{args.dataset}",
        "label": args.label,
        "code_revision": rev,
        "chunks": len(chunks),
        "usable_chunks": sum(c.usable_as_evidence for c in chunks),
        "retrieval_mode": "bm25",
        "provider": "extractive (deterministic; no LLM)",
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "results": result,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"benchmark_v3_{args.label}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for sp in ("dev", "test", "all"):
        r, c = result[sp]["retrieval"], result[sp]["copilot"]
        print(
            f"{sp:4s} P@1={r['precision']['@1']} P@5={r['precision']['@5']} R@5={r['recall']['@5']} "
            f"MRR={r['mrr']} nDCG={r['ndcg@10']} | status={c['status_accuracy']} abst={c['abstention']} "
            f"citeP={c['citation_precision']} citeR={c['citation_recall']} support={c['answer_support']} "
            f"comp={c['comparison_completeness']} ground={c['grounding']} inelig={c['ineligible_citations']}"
        )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
