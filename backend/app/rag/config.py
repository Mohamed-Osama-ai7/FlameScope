"""Environment-driven configuration. No keys or model names are hard-coded (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.data_platform.settings import project_root

PROJECT_ROOT = project_root()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class RagConfig:
    dense_backend: str  # none | hashing | bge-m3
    dense_model: str
    rerank_backend: str  # none | bge
    rerank_model: str
    device: str
    cache_dir: Path
    llm_provider: str  # extractive | openai_compat
    llm_base_url: str
    llm_model: str
    llm_api_key: str  # read from env only; never logged or returned by the API
    llm_timeout_s: float
    rrf_k: int
    hybrid_fusion: str  # rrf | weighted
    bm25_weight: float
    dense_weight: float

    @staticmethod
    def from_env() -> RagConfig:
        return RagConfig(
            dense_backend=_env("FLAMESCOPE_DENSE_BACKEND", "none").lower(),
            dense_model=_env("FLAMESCOPE_DENSE_MODEL", "BAAI/bge-m3"),
            rerank_backend=_env("FLAMESCOPE_RERANK_BACKEND", "none").lower(),
            rerank_model=_env("FLAMESCOPE_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            device=_env("FLAMESCOPE_DEVICE", "cpu"),
            cache_dir=Path(_env("FLAMESCOPE_RAG_CACHE", str(PROJECT_ROOT / "data" / "processed" / "rag"))),
            llm_provider=_env("FLAMESCOPE_LLM_PROVIDER", "extractive").lower(),
            llm_base_url=_env("FLAMESCOPE_LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_model=_env("FLAMESCOPE_LLM_MODEL"),
            llm_api_key=_env("FLAMESCOPE_LLM_API_KEY"),
            llm_timeout_s=float(_env("FLAMESCOPE_LLM_TIMEOUT_S", "60")),
            rrf_k=int(_env("FLAMESCOPE_RRF_K", "60")),
            hybrid_fusion=_env("FLAMESCOPE_HYBRID_FUSION", "rrf").lower(),
            bm25_weight=float(_env("FLAMESCOPE_BM25_WEIGHT", "0.5")),
            dense_weight=float(_env("FLAMESCOPE_DENSE_WEIGHT", "0.5")),
        )
