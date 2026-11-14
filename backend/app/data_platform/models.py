"""SQLAlchemy 2.0 ORM models - the authoritative relational contract.

Alembic migrations (app/data_platform/migrations) are generated from these models and
``database/schema.sql`` is the offline SQL rendering of those migrations (see docs/14).

Provenance chain enforced by NOT NULL foreign keys:

    measurement -> experimental_run -> investigation
         |  \\-> source_artifact (SHA-256, URL, licence, retrieval time)
         |  \\-> extraction_run (extractor name + version + input digests)
         \\-> variable (dimension) + unit (dimension) ; source_row + source_column + original text

Portable types: JSON becomes JSONB on PostgreSQL; Uuid is native on PostgreSQL. Tests also run on
SQLite, so no PostgreSQL-only SQL appears in constraints.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.regimes import CombustionRegime, Dimension

# Stable constraint names so autogenerate and downgrade behave the same on every machine.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONType = JSON().with_variant(JSONB(), "postgresql")
EMPTY_OBJECT = text("'{}'")
EMPTY_LIST = text("'[]'")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class MeasurementRole(str, Enum):
    CONDITION = "condition"  # controlled/ambient condition of the run (pressure, composition, D0)
    OUTCOME = "outcome"  # observed result (K, extinction diameter, burn time)


class ValueStatus(str, Enum):
    PARSED = "parsed"  # numeric, exactly as written in the source
    APPROXIMATE = "approximate"  # numeric, source marked it approximate (e.g. '~6')
    MISSING = "missing"  # blank or explicit missing marker in the source; value is NULL
    UNPARSEABLE = "unparseable"  # source text is not a number; value is NULL, text kept


class ValueOrigin(str, Enum):
    MEASURED = "measured"
    DERIVED = "derived"  # calculated by FlameScope
    REPORT_VALUE = "report_value"  # value reported by the investigators (e.g. FLEX team's fitted K)


class CheckSeverity(str, Enum):
    ERROR = "error"  # structural/integrity problem: the load is refused
    WARNING = "warning"  # scientific anomaly: data kept and flagged
    INFO = "info"


class CheckOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    FLAGGED = "flagged"


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


REGIMES = [r.value for r in CombustionRegime]
DIMENSIONS = [d.value for d in Dimension]
ROLES = [r.value for r in MeasurementRole]
VALUE_STATUSES = [s.value for s in ValueStatus]
VALUE_ORIGINS = [o.value for o in ValueOrigin]
SEVERITIES = [s.value for s in CheckSeverity]
OUTCOMES = [o.value for o in CheckOutcome]


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (CheckConstraint(_in("combustion_regime", REGIMES), name="regime"),)

    investigation_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # = registry source_id
    title: Mapped[str] = mapped_column(Text)
    acronym: Mapped[str | None] = mapped_column(String(64))
    combustion_regime: Mapped[str] = mapped_column(String(64))
    source_repository: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(128))
    license_id: Mapped[str | None] = mapped_column(String(64))
    research_area: Mapped[str | None] = mapped_column(String(128))
    official_challenge_resource: Mapped[bool] = mapped_column(Boolean)
    registry_status: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)

    artifacts: Mapped[list[SourceArtifact]] = relationship(back_populates="investigation")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        UniqueConstraint("relative_path", "sha256", name="uq_source_artifacts_path_sha256"),
        CheckConstraint("byte_size >= 0", name="byte_size_nonnegative"),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.investigation_id"), index=True)
    artifact_kind: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(Text)
    relative_path: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(128))
    text_encoding: Mapped[str | None] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    source_version: Mapped[str | None] = mapped_column(Text)
    license_id: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)

    investigation: Mapped[Investigation] = relationship(back_populates="artifacts")


class Variable(Base):
    __tablename__ = "variables"
    __table_args__ = (CheckConstraint(_in("dimension", DIMENSIONS), name="dimension"),)

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    environmental: Mapped[bool] = mapped_column(Boolean)
    defined_in: Mapped[str] = mapped_column(String(128))


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (CheckConstraint(_in("dimension", DIMENSIONS), name="dimension"),)

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(32))


class ExtractionRun(Base):
    """One extractor version applied to one exact set of input bytes (deterministic id)."""

    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint("run_count >= 0 AND measurement_count >= 0", name="counts_nonnegative"),
    )

    extraction_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_artifacts.artifact_id"), index=True)
    extractor_name: Mapped[str] = mapped_column(String(128))
    extractor_version: Mapped[str] = mapped_column(String(32))
    inputs_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)
    code_revision: Mapped[str | None] = mapped_column(String(64))
    run_count: Mapped[int] = mapped_column(Integer)
    measurement_count: Mapped[int] = mapped_column(Integer)
    first_loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    checks: Mapped[list[DataQualityCheck]] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan", order_by="DataQualityCheck.check_name"
    )


class ExperimentalRun(Base):
    """One test/run as recorded in a source table row. Outcomes live in measurements, never here."""

    __tablename__ = "experimental_runs"
    __table_args__ = (
        UniqueConstraint("artifact_id", "source_row", name="uq_experimental_runs_artifact_row"),
        CheckConstraint(_in("combustion_regime", REGIMES), name="regime"),
        CheckConstraint("source_row >= 1", name="source_row_positive"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.investigation_id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_artifacts.artifact_id"))
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.extraction_run_id"))
    source_row: Mapped[int] = mapped_column(Integer)
    source_identifier: Mapped[str] = mapped_column(String(128), index=True)  # NOT unique upstream
    source_record_key: Mapped[str | None] = mapped_column(
        String(256), unique=True
    )  # = lab dataset record_key
    combustion_regime: Mapped[str] = mapped_column(String(64), index=True)
    material_or_fuel: Mapped[str | None] = mapped_column(String(256))
    test_date: Mapped[date | None] = mapped_column(Date)
    test_date_raw: Mapped[str] = mapped_column(String(32))
    test_time_gmt_raw: Mapped[str] = mapped_column(String(32))
    end_mode: Mapped[str | None] = mapped_column(String(64))
    apparatus: Mapped[str | None] = mapped_column(Text)
    gravity_level_g: Mapped[float | None] = mapped_column(Float)
    source_locator: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text)
    quality_flags: Mapped[list[str]] = mapped_column(JSONType, server_default=EMPTY_LIST)
    # Classifications computed by FlameScope (diluent family, pressure cluster, report cross-reference).
    # Kept apart from source values; every entry names what derived it.
    derived_attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)

    measurements: Mapped[list[Measurement]] = relationship(
        back_populates="run", order_by="Measurement.source_column"
    )


class Measurement(Base):
    """One source cell = one row. Original text is kept verbatim next to the parsed value."""

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("artifact_id", "source_row", "source_column", name="uq_measurements_cell"),
        CheckConstraint(_in("role", ROLES), name="role"),
        CheckConstraint(_in("value_status", VALUE_STATUSES), name="value_status"),
        CheckConstraint(_in("measured_or_derived", VALUE_ORIGINS), name="measured_or_derived"),
        CheckConstraint(
            "(value IS NULL AND value_status IN ('missing', 'unparseable')) OR "
            "(value IS NOT NULL AND value_status IN ('parsed', 'approximate'))",
            name="value_matches_status",
        ),
        CheckConstraint("NOT usable_for_analysis OR value IS NOT NULL", name="usable_requires_value"),
        CheckConstraint(
            "uncertainty_value IS NULL OR uncertainty_value >= 0", name="uncertainty_nonnegative"
        ),
        CheckConstraint("source_row >= 1", name="source_row_positive"),
        Index("ix_measurements_run_variable", "run_id", "variable_name"),
    )

    measurement_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("experimental_runs.run_id"))
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_artifacts.artifact_id"))
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.extraction_run_id"))
    variable_name: Mapped[str] = mapped_column(ForeignKey("variables.name"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    value: Mapped[float | None] = mapped_column(Float)
    value_status: Mapped[str] = mapped_column(String(16))
    original_value_text: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(ForeignKey("units.symbol"))
    original_unit_label: Mapped[str | None] = mapped_column(String(64))
    unit_evidence: Mapped[str | None] = mapped_column(Text)
    timestamp_value: Mapped[float | None] = mapped_column(Float)
    timestamp_unit: Mapped[str | None] = mapped_column(String(32))
    uncertainty_value: Mapped[float | None] = mapped_column(Float)
    uncertainty_type: Mapped[str | None] = mapped_column(String(64))
    coverage_factor: Mapped[float | None] = mapped_column(Float)
    measured_or_derived: Mapped[str] = mapped_column(String(16))
    sensor_or_method: Mapped[str | None] = mapped_column(Text)
    calibration_status: Mapped[str | None] = mapped_column(String(64))
    source_row: Mapped[int] = mapped_column(Integer)
    source_column: Mapped[str] = mapped_column(Text)  # raw header, verbatim
    source_locator: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text)
    usable_for_analysis: Mapped[bool] = mapped_column(Boolean)
    quality_flags: Mapped[list[str]] = mapped_column(JSONType, server_default=EMPTY_LIST)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)

    run: Mapped[ExperimentalRun] = relationship(back_populates="measurements")
    artifact: Mapped[SourceArtifact] = relationship()
    extraction_run: Mapped[ExtractionRun] = relationship()


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"
    __table_args__ = (
        UniqueConstraint("extraction_run_id", "check_name", name="uq_data_quality_checks_run_check"),
        CheckConstraint(_in("severity", SEVERITIES), name="severity"),
        CheckConstraint(_in("outcome", OUTCOMES), name="outcome"),
        CheckConstraint("affected_count >= 0", name="affected_count_nonnegative"),
    )

    check_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.extraction_run_id", ondelete="CASCADE")
    )
    check_name: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(16))
    affected_count: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONType, server_default=EMPTY_OBJECT)

    extraction_run: Mapped[ExtractionRun] = relationship(back_populates="checks")


class AnalysisResult(Base):
    """A computed result, tied to the method card version and (via analysis_result_inputs) its inputs."""

    __tablename__ = "analysis_results"
    __table_args__ = (
        CheckConstraint("computable OR abstention_reason IS NOT NULL", name="abstention_reason"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    method_id: Mapped[str] = mapped_column(String(128))
    method_version: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("experimental_runs.run_id"))
    computable: Mapped[bool] = mapped_column(Boolean)
    abstention_reason: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisResultInput(Base):
    """Join table (replaces the old BIGINT[] column) so every input keeps referential integrity."""

    __tablename__ = "analysis_result_inputs"

    result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_results.result_id", ondelete="CASCADE"), primary_key=True
    )
    measurement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("measurements.measurement_id", ondelete="RESTRICT"), primary_key=True
    )


class DocumentChunk(Base):
    """Retrieval corpus (Retrieval & AI workstream). Populated only from registered source artifacts."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id", "chunker_version", "chunk_index", name="uq_document_chunks_artifact_version_index"
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_artifacts.artifact_id"))
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.investigation_id"))
    combustion_regime: Mapped[str | None] = mapped_column(String(64))
    page_or_section: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    chunker_version: Mapped[str] = mapped_column(String(32))
