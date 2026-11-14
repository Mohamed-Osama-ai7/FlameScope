"""Pydantic response contracts for the provenance-aware API (consumed by the frontend and RAG)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.data_platform.settings import project_root
from app.domain.eligibility import EligibilityPolicy


@lru_cache(maxsize=1)
def _policy() -> EligibilityPolicy:
    return EligibilityPolicy(project_root())


T = TypeVar("T")


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorOut(BaseModel):
    """Body of 404 and 503 errors, and of the 422 raised for an invalid flag filter.

    FastAPI's own request validation (bad UUID, limit out of range) answers 422 with a list in ``detail``.
    """

    detail: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Rows matching the filters, before limit/offset.")
    limit: int
    offset: int


class ArtifactOut(_ORM):
    artifact_id: uuid.UUID
    investigation_id: str
    artifact_kind: str
    file_name: str
    relative_path: str
    media_type: str | None
    text_encoding: str | None
    byte_size: int
    sha256: str
    source_url: str
    source_version: str | None
    license_id: str | None
    retrieved_at: datetime


class InvestigationOut(_ORM):
    investigation_id: str
    title: str
    acronym: str | None
    combustion_regime: str
    source_repository: str
    source_url: str
    doi: str | None
    license_id: str | None
    research_area: str | None
    official_challenge_resource: bool
    registry_status: str
    # scientific evidence decision (data/metadata/source_eligibility.csv), read at response time;
    # PSI-69 is PENDING_VERIFICATION, i.e. usable but not scientifically approved
    evidence_eligibility: str = ""

    @model_validator(mode="after")
    def _eligibility(self) -> InvestigationOut:
        if not self.evidence_eligibility:
            self.evidence_eligibility = _policy().decision(self.investigation_id).eligibility.value
        return self


class InvestigationDetail(InvestigationOut):
    run_count: int
    measurement_count: int
    artifacts: list[ArtifactOut]


class MeasurementOut(_ORM):
    measurement_id: uuid.UUID
    run_id: str
    variable_name: str
    role: str
    value: float | None = Field(description="NULL when the source cell is missing or not a number.")
    value_status: str = Field(description="parsed | approximate | missing | unparseable")
    original_value_text: str = Field(description="Source cell text, verbatim.")
    unit: str
    measured_or_derived: str
    usable_for_analysis: bool
    quality_flags: list[str]
    attributes: dict[str, Any]
    uncertainty_value: float | None
    uncertainty_type: str | None
    coverage_factor: float | None
    source_column: str
    source_locator: str


class RunSummary(_ORM):
    run_id: str
    investigation_id: str
    source_row: int
    source_identifier: str
    source_record_key: str | None = Field(
        description="Join key to records in frontend/public/data/flex_lab_dataset_*.json (record_key)."
    )
    combustion_regime: str
    material_or_fuel: str | None
    test_date: date | None
    test_date_raw: str
    test_time_gmt_raw: str
    end_mode: str | None
    quality_flags: list[str]
    derived_attributes: dict[str, Any]
    source_locator: str


class RunDetail(RunSummary):
    artifact: ArtifactOut
    measurements: list[MeasurementOut]


class ExtractionRunOut(_ORM):
    extraction_run_id: uuid.UUID
    extractor_name: str
    extractor_version: str
    inputs_json: dict[str, Any]
    parameters_json: dict[str, Any]
    code_revision: str | None
    run_count: int
    measurement_count: int
    first_loaded_at: datetime
    last_loaded_at: datetime


class SourceCell(BaseModel):
    file_name: str
    source_row: int
    source_column: str
    original_value_text: str
    original_unit_label: str | None
    platform_unit: str
    unit_evidence: str | None
    source_locator: str


class ProvenanceOut(BaseModel):
    """Everything needed to trace one number back to the original NASA bytes."""

    measurement: MeasurementOut
    source_cell: SourceCell
    run: RunSummary
    investigation: InvestigationOut
    artifact: ArtifactOut
    extraction: ExtractionRunOut
    extraction_method: str
    how_to_verify: str


class VariableOut(_ORM):
    name: str
    dimension: str
    description: str
    environmental: bool
    defined_in: str
    measurement_count: int = 0


class UnitOut(_ORM):
    symbol: str
    dimension: str


class QualityCheckOut(_ORM):
    check_name: str
    severity: str
    outcome: str
    affected_count: int
    description: str
    details_json: dict[str, Any]


class QualityReportOut(BaseModel):
    investigation_id: str
    artifact_sha256: str
    extraction: ExtractionRunOut
    load_blocked: bool = Field(description="Always false for stored reports: blocked loads write nothing.")
    counts: dict[str, int]
    checks: list[QualityCheckOut]


class DataPlatformStatus(BaseModel):
    database_configured: bool
    database_reachable: bool
    schema_revision: str | None
    expected_schema_revision: str
    investigations_loaded: list[str]
    official_challenge_resource_loaded: bool
    runs: int
    measurements: int
    detail: str | None = None
