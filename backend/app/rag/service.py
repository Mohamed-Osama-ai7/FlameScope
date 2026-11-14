"""Process-wide wiring of corpus, retriever and Copilot (built lazily, once, from the environment)."""

from __future__ import annotations

from functools import lru_cache

from app.rag.config import RagConfig
from app.rag.copilot import ScientificCopilot
from app.rag.dense import make_encoder
from app.rag.ingest import build_corpus
from app.rag.llm import make_provider
from app.rag.rerank import make_reranker
from app.rag.retriever import HybridRetriever


def build_retriever(cfg: RagConfig) -> HybridRetriever:
    return HybridRetriever(build_corpus(), cfg, make_encoder(cfg), make_reranker(cfg))


@lru_cache(maxsize=1)
def get_copilot() -> ScientificCopilot:
    cfg = RagConfig.from_env()
    return ScientificCopilot(build_retriever(cfg), make_provider(cfg))


def reset_service() -> None:
    get_copilot.cache_clear()
