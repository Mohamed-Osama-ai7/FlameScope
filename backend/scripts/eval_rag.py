"""Run the RAG/Copilot evaluation and write reports/rag_eval/results_<label>.json (+ markdown summary).

    python scripts/eval_rag.py                      # bm25 baseline, then dense and hybrid rows
    FLAMESCOPE_DENSE_BACKEND=bge-m3 python scripts/eval_rag.py --dense bge-m3

Nothing is hard-coded: results are whatever this machine measures; the backend name is stored with each row.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.config import RagConfig  # noqa: E402
from app.rag.copilot import ScientificCopilot  # noqa: E402
from app.rag.dense import make_encoder  # noqa: E402
from app.rag.evaluation import (  # noqa: E402
    flagged_sweep,
    load_questions,
    run_all,
    safety_metrics,
    verify_gold,
)
from app.rag.ingest import build_corpus, load_flex  # noqa: E402
from app.rag.llm import ExtractiveProvider  # noqa: E402
from app.rag.rerank import make_reranker  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dense", default="hashing", help="dense backend for the dense/hybrid rows: hashing | bge-m3"
    )
    ap.add_argument(
        "--rerank", action="store_true", help="also evaluate with the BGE reranker (needs weights)"
    )
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "rag_eval")
    ap.add_argument("--label", default=None)
    ap.add_argument("--dataset", default="rag_questions_v2.jsonl", help="file under backend/eval/")
    ap.add_argument("--no-safety", action="store_true", help="skip the safety suite and flagged sweep")
    args = ap.parse_args(argv)

    chunks = build_corpus(ROOT)
    questions = load_questions(ROOT / "backend" / "eval" / args.dataset)
    problems = verify_gold(questions, chunks)
    if problems:
        print("GOLD LABEL PROBLEMS:\n" + "\n".join(problems))
        return 2

    base = RagConfig.from_env()
    cache: dict[str, HybridRetriever] = {}

    def retr(backend: str, _mode: str) -> HybridRetriever:
        if backend not in cache:
            cfg = replace(base, dense_backend=backend)
            cache[backend] = HybridRetriever(chunks, cfg, make_encoder(cfg), make_reranker(cfg))
        return cache[backend]

    configs = [
        ("bm25", "none", "bm25", False),
        (f"dense[{args.dense}]", args.dense, "dense", False),
        (f"hybrid-rrf[{args.dense}]", args.dense, "hybrid", False),
    ]
    if args.rerank:
        configs.append((f"hybrid-rrf+rerank[{args.dense}]", args.dense, "hybrid", True))
    results = run_all(retr, lambda r: ScientificCopilot(r, ExtractiveProvider()), questions, configs)
    safety: dict[str, object] = {}
    if not args.no_safety:
        cop = ScientificCopilot(retr("none", "bm25"), ExtractiveProvider())
        cases = load_questions(ROOT / "backend" / "eval" / "rag_safety_v1.jsonl")
        safety = {
            "suite": safety_metrics(cop, cases),
            "flagged_sweep": flagged_sweep(cop, load_flex(ROOT)[2]),
        }
    payload = {
        "dataset": f"backend/eval/{args.dataset}",
        "questions": len(questions),
        "answerable": sum(q["answerable"] for q in questions),
        "chunks": len(chunks),
        "usable_chunks": sum(c.usable_as_evidence for c in chunks),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "provider": "extractive (deterministic; no LLM was used in this evaluation)",
        "results": results,
        "safety": safety,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    label = args.label or ("v2_" + args.dense.replace("/", "_"))
    path = args.out / f"results_{label}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")
    for name, r in results.items():
        for sp in ("dev", "test", "all"):
            rt = r["splits"][sp]["retrieval"]
            cp = r["splits"][sp]["copilot"]
            print(
                f"{name:28s} {sp:4s} R@1={rt['recall']['@1']:.3f} R@5={rt['recall']['@5']:.3f} "
                f"R@10={rt['recall']['@10']:.3f} MRR={rt['mrr']:.3f} nDCG@10={rt['ndcg@10']:.3f} | "
                f"false-abst={cp['false_abstention_rate']} "
                f"correct-abst={cp['correct_abstention_rate_on_unanswerable']} "
                f"cite-gold={cp['citation_correctness_any_gold']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
