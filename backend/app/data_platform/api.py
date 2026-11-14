"""Provenance-aware read API over the scientific database (mounted under /api/v1).

Contract rules:
* Read-only. Lists are paginated ({items, total, limit, offset}) and deterministically ordered.
* Every measurement exposes its original text, value status, usability and quality flags, and
  ``/measurements/{id}/provenance`` resolves it to artifact SHA-256 + row + column + extractor version.
* No database -> 503 with an explicit message (never empty or invented data). Unknown id -> 404.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.data_platform.analysis_store import USABLE_REGISTRY_STATUSES
from app.data_platform.db import DatabaseNotConfigured, get_engine, get_session
from app.data_platform.models import (
    DataQualityCheck,
    ExperimentalRun,
    ExtractionRun,
    Investigation,
    Measurement,
    SourceArtifact,
    Unit,
    Variable,
)
from app.data_platform.schema_version import current_revision, expected_head
from app.data_platform.schemas import (
    ArtifactOut,
    DataPlatformStatus,
    ErrorOut,
    ExtractionRunOut,
    InvestigationDetail,
    InvestigationOut,
    MeasurementOut,
    Page,
    ProvenanceOut,
    QualityCheckOut,
    QualityReportOut,
    RunDetail,
    RunSummary,
    SourceCell,
    UnitOut,
    VariableOut,
)

router = APIRouter(
    tags=["scientific data"],
    responses={503: {"model": ErrorOut, "description": "Scientific database not configured or unreachable"}},
)
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut, "description": "Unknown id"}}
SessionDep = Annotated[Session, Depends(get_session)]
_FLAG = re.compile(r"^[a-z0-9_.:]{1,80}$")


def _flag_param(value: str | None) -> str | None:
    if value is not None and not _FLAG.match(value):
        raise HTTPException(status_code=422, detail="flag must match ^[a-z0-9_.:]{1,80}$")
    return value


def _json_list_contains(session: Session, column: Any, flag: str) -> ColumnElement[bool]:
    if session.get_bind().dialect.name == "postgresql":
        return type_coerce(column, JSONB).contains([flag])
    return cast(column, String).like(f'%"{flag}"%')  # portable fallback (SQLite tests)


def _page(session: Session, stmt: Any, limit: int, offset: int) -> tuple[list[Any], int]:
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(session.scalars(stmt.limit(limit).offset(offset)))
    return rows, total


# ------------------------------------------------------------------ status


def platform_status() -> DataPlatformStatus:
    """Never raises: reports configuration/reachability instead."""
    head = expected_head()

    def not_loaded(
        configured: bool, reachable: bool, detail: str, revision: str | None = None
    ) -> DataPlatformStatus:
        return DataPlatformStatus(
            database_configured=configured,
            database_reachable=reachable,
            schema_revision=revision,
            expected_schema_revision=head,
            investigations_loaded=[],
            official_challenge_resource_loaded=False,
            runs=0,
            measurements=0,
            detail=detail,
        )

    try:
        engine = get_engine()
    except DatabaseNotConfigured as exc:
        return not_loaded(False, False, str(exc))
    try:
        revision = current_revision(engine)
        if revision != head:
            return not_loaded(True, True, "schema not at head; run `alembic upgrade head`", revision)
        with Session(engine) as session:
            loaded = list(
                session.execute(
                    select(Investigation.investigation_id, Investigation.official_challenge_resource)
                    .join(ExperimentalRun, ExperimentalRun.investigation_id == Investigation.investigation_id)
                    .where(Investigation.registry_status.in_(USABLE_REGISTRY_STATUSES))
                    .group_by(Investigation.investigation_id, Investigation.official_challenge_resource)
                    .order_by(Investigation.investigation_id)
                )
            )
            runs = session.scalar(select(func.count()).select_from(ExperimentalRun)) or 0
            measurements = session.scalar(select(func.count()).select_from(Measurement)) or 0
    except SQLAlchemyError as exc:
        return not_loaded(True, False, f"database unreachable: {type(exc).__name__}")
    return DataPlatformStatus(
        database_configured=True,
        database_reachable=True,
        schema_revision=revision,
        expected_schema_revision=head,
        investigations_loaded=[row[0] for row in loaded],
        official_challenge_resource_loaded=any(row[1] for row in loaded),
        runs=runs,
        measurements=measurements,
    )


@router.get("/data-platform/status", response_model=DataPlatformStatus)
def data_platform_status() -> DataPlatformStatus:
    return platform_status()


# ------------------------------------------------------------------ investigations


@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(session: SessionDep) -> list[Investigation]:
    return list(session.scalars(select(Investigation).order_by(Investigation.investigation_id)))


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail, responses=NOT_FOUND)
def get_investigation(investigation_id: str, session: SessionDep) -> InvestigationDetail:
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"investigation {investigation_id!r} not loaded")
    runs = session.scalar(
        select(func.count())
        .select_from(ExperimentalRun)
        .where(ExperimentalRun.investigation_id == investigation_id)
    )
    measurements = session.scalar(
        select(func.count())
        .select_from(Measurement)
        .join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id)
        .where(ExperimentalRun.investigation_id == investigation_id)
    )
    artifacts = session.scalars(
        select(SourceArtifact)
        .where(SourceArtifact.investigation_id == investigation_id)
        .order_by(SourceArtifact.retrieved_at, SourceArtifact.relative_path)
    )
    return InvestigationDetail(
        **InvestigationOut.model_validate(inv).model_dump(),
        run_count=runs or 0,
        measurement_count=measurements or 0,
        artifacts=[ArtifactOut.model_validate(a) for a in artifacts],
    )


# ------------------------------------------------------------------ runs


@router.get("/runs", response_model=Page[RunSummary])
def list_runs(
    session: SessionDep,
    investigation_id: str | None = None,
    combustion_regime: str | None = None,
    fuel: str | None = Query(None, description="Exact material_or_fuel, e.g. Heptane"),
    end_mode: str | None = Query(None, description="Exact end mode, e.g. Extinction"),
    has_flag: str | None = Query(None, description="Only runs carrying this run-level quality flag"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[RunSummary]:
    stmt = select(ExperimentalRun).order_by(ExperimentalRun.investigation_id, ExperimentalRun.source_row)
    if investigation_id:
        stmt = stmt.where(ExperimentalRun.investigation_id == investigation_id)
    if combustion_regime:
        stmt = stmt.where(ExperimentalRun.combustion_regime == combustion_regime)
    if fuel:
        stmt = stmt.where(ExperimentalRun.material_or_fuel == fuel)
    if end_mode:
        stmt = stmt.where(ExperimentalRun.end_mode == end_mode)
    if flag := _flag_param(has_flag):
        stmt = stmt.where(_json_list_contains(session, ExperimentalRun.quality_flags, flag))
    rows, total = _page(session, stmt, limit, offset)
    return Page[RunSummary](
        items=[RunSummary.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/runs/{run_id}", response_model=RunDetail, responses=NOT_FOUND)
def get_run(run_id: str, session: SessionDep) -> RunDetail:
    run = session.scalar(
        select(ExperimentalRun)
        .where(ExperimentalRun.run_id == run_id)
        .options(selectinload(ExperimentalRun.measurements))
    )
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    artifact = session.get(SourceArtifact, run.artifact_id)
    assert artifact is not None  # FK guarantees it
    return RunDetail(
        **RunSummary.model_validate(run).model_dump(),
        artifact=ArtifactOut.model_validate(artifact),
        measurements=[MeasurementOut.model_validate(m) for m in run.measurements],
    )


# ------------------------------------------------------------------ measurements


@router.get("/measurements", response_model=Page[MeasurementOut], responses=NOT_FOUND)
def list_measurements(
    session: SessionDep,
    investigation_id: str | None = None,
    run_id: str | None = None,
    variable: str | None = Query(None, description="Variable name, e.g. burning_rate_constant_mm2_s"),
    role: str | None = Query(None, pattern="^(condition|outcome)$"),
    value_status: str | None = Query(None, pattern="^(parsed|approximate|missing|unparseable)$"),
    usable_only: bool = Query(
        True,
        description=(
            "Default true (safe for analysis and RAG): only values with usable_for_analysis = true, i.e. "
            "a numeric value, no blocking flag, and a source that is not withdrawn. Set false to inspect "
            "missing or invalid cells."
        ),
    ),
    exclude_flag: Annotated[
        list[str] | None, Query(description="Drop measurements carrying any of these flags")
    ] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Page[MeasurementOut]:
    stmt = select(Measurement).order_by(Measurement.run_id, Measurement.variable_name)
    if investigation_id:
        stmt = stmt.join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id).where(
            ExperimentalRun.investigation_id == investigation_id
        )
    if run_id:
        stmt = stmt.where(Measurement.run_id == run_id)
    if variable:
        if session.get(Variable, variable) is None:
            raise HTTPException(
                status_code=404, detail=f"unknown variable {variable!r}; see /api/v1/variables"
            )
        stmt = stmt.where(Measurement.variable_name == variable)
    if role:
        stmt = stmt.where(Measurement.role == role)
    if value_status:
        stmt = stmt.where(Measurement.value_status == value_status)
    if usable_only:
        stmt = stmt.where(Measurement.usable_for_analysis.is_(True))
    for flag in exclude_flag or []:
        stmt = stmt.where(~_json_list_contains(session, Measurement.quality_flags, _flag_param(flag) or ""))
    rows, total = _page(session, stmt, limit, offset)
    return Page[MeasurementOut](
        items=[MeasurementOut.model_validate(m) for m in rows], total=total, limit=limit, offset=offset
    )


def _measurement(session: Session, measurement_id: uuid.UUID) -> Measurement:
    m = session.get(Measurement, measurement_id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"measurement {measurement_id} not found")
    return m


@router.get("/measurements/{measurement_id}", response_model=MeasurementOut, responses=NOT_FOUND)
def get_measurement(measurement_id: uuid.UUID, session: SessionDep) -> Measurement:
    return _measurement(session, measurement_id)


@router.get("/measurements/{measurement_id}/provenance", response_model=ProvenanceOut, responses=NOT_FOUND)
def get_provenance(measurement_id: uuid.UUID, session: SessionDep) -> ProvenanceOut:
    m = _measurement(session, measurement_id)
    run, artifact, extraction = m.run, m.artifact, m.extraction_run
    investigation = session.get(Investigation, run.investigation_id)
    assert investigation is not None
    return ProvenanceOut(
        measurement=MeasurementOut.model_validate(m),
        source_cell=SourceCell(
            file_name=artifact.file_name,
            source_row=m.source_row,
            source_column=m.source_column,
            original_value_text=m.original_value_text,
            original_unit_label=m.original_unit_label,
            platform_unit=m.unit,
            unit_evidence=m.unit_evidence,
            source_locator=m.source_locator,
        ),
        run=RunSummary.model_validate(run),
        investigation=InvestigationOut.model_validate(investigation),
        artifact=ArtifactOut.model_validate(artifact),
        extraction=ExtractionRunOut.model_validate(extraction),
        extraction_method=m.extraction_method,
        how_to_verify=(
            f"Download {artifact.source_url}, check SHA-256 = {artifact.sha256}, decode as "
            f"{artifact.text_encoding or 'utf-8'}, parse as CSV, then read the line given by csv_line in "
            f"source_locator (data row {m.source_row}) in column '{m.source_column}'."
        ),
    )


# ------------------------------------------------------------------ vocabulary & quality


@router.get("/variables", response_model=list[VariableOut])
def list_variables(session: SessionDep) -> list[VariableOut]:
    counts: dict[str, int] = {
        name: n
        for name, n in session.execute(
            select(Measurement.variable_name, func.count()).group_by(Measurement.variable_name)
        ).tuples()
    }
    return [
        VariableOut.model_validate(v).model_copy(update={"measurement_count": counts.get(v.name, 0)})
        for v in session.scalars(select(Variable).order_by(Variable.name))
    ]


@router.get("/units", response_model=list[UnitOut])
def list_units(session: SessionDep) -> list[Unit]:
    return list(session.scalars(select(Unit).order_by(Unit.symbol)))


@router.get("/data-quality/{investigation_id}", response_model=QualityReportOut, responses=NOT_FOUND)
def quality_report(investigation_id: str, session: SessionDep) -> QualityReportOut:
    """Checks recorded by the latest load of this investigation's current artifact."""
    row = session.execute(
        select(ExtractionRun, SourceArtifact)
        .join(SourceArtifact, ExtractionRun.artifact_id == SourceArtifact.artifact_id)
        .join(ExperimentalRun, ExperimentalRun.extraction_run_id == ExtractionRun.extraction_run_id)
        .where(SourceArtifact.investigation_id == investigation_id)
        .order_by(ExtractionRun.last_loaded_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no load recorded for {investigation_id!r}")
    extraction, artifact = row
    checks = list(
        session.scalars(
            select(DataQualityCheck)
            .where(DataQualityCheck.extraction_run_id == extraction.extraction_run_id)
            .order_by(DataQualityCheck.severity, DataQualityCheck.check_name)
        )
    )
    counts: dict[str, int] = {}
    for c in checks:
        key = f"{c.severity}_{c.outcome}"
        counts[key] = counts.get(key, 0) + 1
    return QualityReportOut(
        investigation_id=investigation_id,
        artifact_sha256=artifact.sha256,
        extraction=ExtractionRunOut.model_validate(extraction),
        load_blocked=False,
        counts=dict(sorted(counts.items())),
        checks=[QualityCheckOut.model_validate(c) for c in checks],
    )
