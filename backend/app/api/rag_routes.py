"""HTTP surface of the Scientific Intelligence Layer (additive; existing routes are untouched).

Public routes never return ineligible evidence (PSI-25 excluded, PSI-98 quarantined, unregistered
NASA/TP captions): /rag/search filters them out and /rag/chunks answers 403 with the eligibility status.
Exclusion reasons and the excluded text are available only under /rag/admin, which is disabled unless
FLAMESCOPE_RAG_ADMIN_TOKEN is set and the request carries it in X-FlameScope-Admin-Token.
"""

from __future__ import annotations

import hmac
import os
from collections import Counter

from fastapi import APIRouter, Header, HTTPException

from app.rag.config import PROJECT_ROOT, RagConfig
from app.rag.copilot import CopilotRequest, CopilotResponse
from app.rag.dense import DenseUnavailableError
from app.rag.eligibility import EligibilityPolicy
from app.rag.ingest import IngestError
from app.rag.llm import LLMUnavailableError
from app.rag.platform import platform_state
from app.rag.schemas import Chunk, SearchRequest, SearchResponse
from app.rag.service import get_copilot
from app.rag.tools import tool_catalog

router = APIRouter(prefix="/rag", tags=["rag"])
copilot_router = APIRouter(prefix="/copilot", tags=["copilot"])
admin_router = APIRouter(prefix="/rag/admin", tags=["rag-admin"])

ADMIN_TOKEN_ENV = "FLAMESCOPE_RAG_ADMIN_TOKEN"


def _svc():
    try:
        return get_copilot()
    except (IngestError, DenseUnavailableError, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/status")
def rag_status() -> dict[str, object]:
    s = _svc()
    cfg = RagConfig.from_env()
    ch = s.retriever.chunks
    return {
        "chunks": len(ch),
        "usable_chunks": sum(c.usable_as_evidence for c in ch),
        "by_source_and_eligibility": dict(Counter(f"{c.source_id}/{c.eligibility}" for c in ch)),
        "by_source_and_type": dict(Counter(f"{c.source_id}/{c.doc_type.value}" for c in ch)),
        "ingestion_version": ch[0].ingestion_version if ch else None,
        "chunker_version": ch[0].chunker_version if ch else None,
        "dense_backend": s.retriever.dense_backend,
        "reranker": s.retriever.reranker.name if s.retriever.reranker else "none",
        "llm_provider": s.provider.name,
        "llm_key_configured": bool(cfg.llm_api_key),  # never the key itself
        "hybrid_fusion": cfg.hybrid_fusion,
        "data_platform": platform_state(),
        "admin_routes_enabled": bool(os.environ.get(ADMIN_TOKEN_ENV)),
    }


@router.get("/sources")
def sources() -> list[dict[str, object]]:
    """Eligibility of every known source (status only; reasons are on the admin route)."""
    return [
        {
            "source_id": d.source_id,
            "eligibility": d.eligibility.value,
            "usable_as_evidence": d.usable_as_evidence,
            "registry_status": d.registry_status,
            "decision_owner": d.decision_owner,
            "decided_on": d.decided_on,
        }
        for d in EligibilityPolicy(PROJECT_ROOT).all_decisions()
    ]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    return _svc().retriever.search(req)  # ineligible chunks are never candidates


@router.get("/chunks/{chunk_ref:path}", response_model=Chunk)
def get_chunk(chunk_ref: str) -> Chunk:
    c = _svc().retriever.get(chunk_ref)
    if c is None:
        raise HTTPException(status_code=404, detail="unknown chunk")
    if not c.usable_as_evidence:
        raise HTTPException(
            status_code=403,
            detail={
                "chunk_id": c.chunk_id,
                "source_id": c.source_id,
                "eligibility": c.eligibility,
                "message": "not available as evidence; exclusion details are on the admin route",
            },
        )
    return c


@router.get("/tools")
def tools() -> list[dict[str, object]]:
    return tool_catalog()


@copilot_router.post("/ask", response_model=CopilotResponse)
def ask(req: CopilotRequest) -> CopilotResponse:
    return _svc().ask(req)


# ------------------------------------------------------------------ admin / audit (token-gated)


def _admin(token: str | None) -> None:
    expected = os.environ.get(ADMIN_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")  # disabled: indistinguishable from absent
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="admin token required")


@admin_router.get("/excluded")
def excluded(x_flamescope_admin_token: str | None = Header(default=None)) -> dict[str, object]:
    _admin(x_flamescope_admin_token)
    ch = [c for c in _svc().retriever.chunks if not c.usable_as_evidence]
    return {
        "sources": [
            {
                "source_id": d.source_id,
                "eligibility": d.eligibility.value,
                "registry_status": d.registry_status,
                "reason": d.reason,
                "decision_owner": d.decision_owner,
                "decided_on": d.decided_on,
            }
            for d in EligibilityPolicy(PROJECT_ROOT).all_decisions()
            if not d.usable_as_evidence
        ],
        "excluded_chunks": dict(Counter(c.source_id for c in ch)),
    }


@admin_router.get("/chunks/{chunk_ref:path}", response_model=Chunk)
def admin_chunk(chunk_ref: str, x_flamescope_admin_token: str | None = Header(default=None)) -> Chunk:
    _admin(x_flamescope_admin_token)
    c = _svc().retriever.get(chunk_ref)
    if c is None:
        raise HTTPException(status_code=404, detail="unknown chunk")
    return c


@admin_router.post("/search", response_model=SearchResponse)
def admin_search(
    req: SearchRequest, x_flamescope_admin_token: str | None = Header(default=None)
) -> SearchResponse:
    """Audit search over ALL chunks; every hit keeps its eligibility and exclusion reason."""
    _admin(x_flamescope_admin_token)
    return _svc().retriever.search(req, include_ineligible=True)
