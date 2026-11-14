"""Typed contracts for the evidence layer. Every chunk carries full provenance (docs/14)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

INGESTION_VERSION = "ingest-1.1.0"  # 1.1: eligibility policy, platform ids, measurement statements
CHUNKER_VERSION = "chunker-1.1.0"  # 1.1: table rows rendered one statement per measurement


class DocType(str, Enum):
    PSI_METADATA = "psi_metadata"  # narrative fields of a PSI investigation record
    REPORT_CAPTION = "report_caption"  # NASA/TP-2015-216046 Appendix B per-test figure caption
    TABLE_ROW = "table_row"  # one row of an acquired PSI experimental table (kept intact)
    TEXT_DOCUMENT = "text_document"  # generic page/section document (PDF/markdown adapter)


class MeasurementRef(BaseModel):
    """A Data Platform measurement stated in a table-row chunk (ids follow the platform contract)."""

    measurement_id: str
    run_id: str
    variable: str
    unit: str
    evidence_status: str  # CLEAN | QUALIFIED | INVALID | MISSING (app/rag/measurements.py)
    original_value_text: str
    value: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    source_column: str
    source_locator: str
    statement: str  # verbatim sentence of the chunk text that states this measurement


class Chunk(BaseModel):
    chunk_id: str  # UUID; equals document_chunks.chunk_id (app/rag/ids.py)
    chunk_key: str  # human-readable key, e.g. PSI-69:row:070 (stable across versions)
    artifact_id: str  # UUID of the source artifact (platform formula)
    artifact_path: str = ""  # repository-relative path of that artifact
    chunk_index: int = 0  # position within (artifact_id, chunker_version)
    source_id: str
    source_title: str
    source_url: str = ""
    doi: str = ""
    license: str = ""
    doc_type: DocType
    regime: str | None = None  # CombustionRegime value; None when not regime-specific
    fuel_or_material: str | None = None
    experiment_ids: list[str] = Field(default_factory=list)  # e.g. FLEX-070, 193F001, PSI row key
    locator: dict[str, str | int | None] = Field(default_factory=dict)  # page/section/table/row
    locator_text: str = ""  # human-readable: "NASA/TP-2015-216046, Appendix B, Fig. 5 (PDF p. 35)"
    text: str
    content_hash: str  # sha256 of `text`
    source_artifact_sha256: str = ""  # hash of the acquired artifact this chunk was parsed from
    verification_status: str = ""  # registry status of the source ("" = not registered)
    eligibility: str = ""  # app/rag/eligibility.py: VERIFIED_ELIGIBLE, PENDING_VERIFICATION, ...
    exclusion_reason: str = ""  # why the source is not usable (empty when usable)
    usable_as_evidence: bool = False  # derived from eligibility; default deny
    quality_flags: list[str] = Field(default_factory=list)
    measurements: list[MeasurementRef] = Field(default_factory=list)
    ingestion_version: str = INGESTION_VERSION
    chunker_version: str = CHUNKER_VERSION


class SearchFilter(BaseModel):
    """Public filters. There is deliberately no switch to include ineligible evidence: excluded chunks are
    reachable only through the admin routes (FLAMESCOPE_RAG_ADMIN_TOKEN). Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] | None = None
    regimes: list[str] | None = None
    doc_types: list[DocType] | None = None
    fuels: list[str] | None = None
    experiment_ids: list[str] | None = None


class SearchHit(BaseModel):
    rank: int
    score: float
    chunk: Chunk
    component_scores: dict[str, float] = Field(default_factory=dict)


RetrievalMode = Literal["bm25", "dense", "hybrid"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    mode: RetrievalMode = "bm25"
    rerank: bool = False
    filters: SearchFilter = Field(default_factory=SearchFilter)


class SearchResponse(BaseModel):
    query: str
    mode: str
    dense_backend: str
    reranked: bool
    hits: list[SearchHit]
    warnings: list[str] = Field(default_factory=list)
