"""Shared fixtures for the RAG/Copilot tests (corpus is built once per session from the acquired sources)."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

import pytest

from app.rag.config import PROJECT_ROOT, RagConfig
from app.rag.copilot import ScientificCopilot
from app.rag.dense import HashingEncoder
from app.rag.ingest import build_corpus
from app.rag.retriever import HybridRetriever
from app.rag.schemas import Chunk


class ScriptedProvider:
    """Test double: returns queued JSON outputs; records the payloads it was given."""

    name = "scripted-test-provider"

    def __init__(self, *outputs: dict[str, Any]) -> None:
        self.outputs = list(outputs)
        self.payloads: list[dict[str, Any]] = []

    def complete(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


@pytest.fixture(scope="session")
def rag_chunks() -> list[Chunk]:
    return build_corpus(PROJECT_ROOT)


@pytest.fixture(scope="session")
def rag_cfg(tmp_path_factory: pytest.TempPathFactory) -> RagConfig:
    return replace(
        RagConfig.from_env(),
        dense_backend="hashing",
        rerank_backend="none",
        llm_provider="extractive",
        llm_api_key="",
        cache_dir=tmp_path_factory.mktemp("rag_cache"),
    )


@pytest.fixture(scope="session")
def retriever(rag_chunks: list[Chunk], rag_cfg: RagConfig) -> HybridRetriever:
    return HybridRetriever(rag_chunks, rag_cfg, HashingEncoder())


@pytest.fixture()
def make_copilot(retriever: HybridRetriever):
    def _make(provider: Any) -> ScientificCopilot:
        return ScientificCopilot(retriever, provider)

    return _make


# ------------------------------------------------------------------ strict raw-data mode (release gate)

RAW_REQUIRED_ENV = "FLAMESCOPE_REQUIRE_RAW_DATA"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # type: ignore[no-untyped-def]
    """With FLAMESCOPE_REQUIRE_RAW_DATA=1 a skip caused by absent raw NASA data becomes a failure, so a
    release run cannot pass silently without the data. Other skips (PostgreSQL, BGE) are unaffected."""
    outcome = yield
    rep = outcome.get_result()
    if rep.skipped and os.environ.get(RAW_REQUIRED_ENV) == "1":
        reason = str(rep.longrepr[-1]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        if "not present" in reason:
            rep.outcome = "failed"
            rep.longrepr = f"{RAW_REQUIRED_ENV}=1 but raw data is missing: {reason}"
