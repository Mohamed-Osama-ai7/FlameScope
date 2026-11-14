"""Optional cross-encoder reranking (BGE reranker v2-m3). Disabled unless explicitly configured."""

from __future__ import annotations

from typing import Protocol

from app.rag.config import RagConfig
from app.rag.dense import DenseUnavailableError


class Reranker(Protocol):
    name: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class BGEReranker:
    def __init__(self, model: str, device: str) -> None:
        try:
            from sentence_transformers import CrossEncoder  # optional: pip install '.[rag]'
        except ImportError as exc:
            raise DenseUnavailableError(
                "BGE reranker needs 'sentence-transformers' and the model weights"
            ) from exc
        self.name = f"{model} (CrossEncoder)"
        self._m = CrossEncoder(model, device=device)

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self._m.predict([(query, t) for t in texts])]


def make_reranker(cfg: RagConfig) -> Reranker | None:
    if cfg.rerank_backend in ("none", ""):
        return None
    if cfg.rerank_backend == "bge":
        return BGEReranker(cfg.rerank_model, cfg.device)
    raise DenseUnavailableError(f"unknown FLAMESCOPE_RERANK_BACKEND '{cfg.rerank_backend}'")
