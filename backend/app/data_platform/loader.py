"""Reproducible, idempotent database loader.

* Everything is written in ONE transaction: a failure leaves the database exactly as it was.
* Primary keys are deterministic, so loading the same bytes twice yields identical rows (only
  ``extraction_runs.last_loaded_at`` / ``code_revision`` change).
* Rows that disappear from a source (e.g. a new PSI file version) are deleted; a measurement that an
  analysis result still references cannot be deleted (FK RESTRICT) and the whole load is rolled back.
* Sources that are QUARANTINED / not acquired are refused; nothing is written for them.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.data_platform import extract_flex, ids
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
from app.data_platform.schema_version import expected_head
from app.data_platform.settings import manifest_path, registry_path
from app.data_platform.vocabulary import unit_specs, variable_specs
from app.domain.eligibility import EligibilityPolicy
from app.domain.sources import SourceRecord, find_source, load_registry

# source_id -> extractor. Sources without an extractor are reported, never silently skipped.
EXTRACTORS = {extract_flex.SOURCE_ID: extract_flex}
NOT_LOADED_REASONS = {
    "PSI-25": (
        "No extractor yet: BASS-II table has free-text materials, censored CO values ('>500', 'OR') and "
        "display readings that need curation by the science lead (data/metadata/variable_dictionary.csv)."
    ),
}


class SchemaNotReady(RuntimeError):
    pass


@dataclass
class SourceLoadResult:
    source_id: str
    loaded: bool
    reason: str = ""
    runs: int = 0
    measurements: int = 0
    deleted_runs: int = 0
    deleted_measurements: int = 0
    warnings: list[str] = field(default_factory=list)
    extraction_run_id: str | None = None


@dataclass
class LoadReport:
    results: list[SourceLoadResult]

    @property
    def ok(self) -> bool:
        return all(r.loaded for r in self.results if r.source_id in EXTRACTORS)


def git_revision(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    rev = out.stdout.strip()
    return rev if len(rev) == 40 else None


def assert_schema_at_head(session: Session) -> None:
    """Refuse to load into a database whose schema is not the current Alembic head."""
    head = expected_head()
    try:
        current = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError as exc:  # table missing
        session.rollback()
        raise SchemaNotReady("database has no alembic_version table; run `alembic upgrade head`") from exc
    session.rollback()  # end the read-only autobegun transaction; the load opens its own
    if current != head:
        raise SchemaNotReady(
            f"database schema is at {current!r}, code expects {head!r}; run `alembic upgrade head`"
        )


def seed_vocabulary(session: Session) -> None:
    for v in variable_specs():
        session.merge(
            Variable(
                name=v.name,
                dimension=v.dimension,
                description=v.description,
                environmental=v.environmental,
                defined_in=v.defined_in,
            )
        )
    for symbol, dimension in unit_specs().items():
        session.merge(Unit(symbol=symbol, dimension=dimension))
    session.flush()


def _load_bundle(session: Session, bundle: extract_flex.ExtractionBundle) -> tuple[int, int]:
    session.merge(Investigation(**bundle.investigation))
    session.merge(SourceArtifact(**bundle.artifact))
    session.flush()

    er = bundle.extraction_run
    existing = session.get(ExtractionRun, er["extraction_run_id"])
    if existing is None:
        session.add(ExtractionRun(**er))
    else:  # same extractor version on the same bytes: keep first_loaded_at
        existing.code_revision = er["code_revision"]
        existing.last_loaded_at = er["last_loaded_at"]
        existing.run_count = er["run_count"]
        existing.measurement_count = er["measurement_count"]
    session.flush()

    investigation_id = bundle.investigation["investigation_id"]
    new_run_ids = {r["run_id"] for r in bundle.runs}
    new_measurement_ids = {m["measurement_id"] for m in bundle.measurements}

    # Stale rows first (a newer file version can drop rows), then upsert.
    run_ids_in_db = set(
        session.scalars(
            select(ExperimentalRun.run_id).where(ExperimentalRun.investigation_id == investigation_id)
        )
    )
    stale_measurements = [
        mid
        for mid in session.scalars(
            select(Measurement.measurement_id)
            .join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id)
            .where(ExperimentalRun.investigation_id == investigation_id)
        )
        if mid not in new_measurement_ids
    ]
    for chunk_start in range(0, len(stale_measurements), 500):
        chunk = stale_measurements[chunk_start : chunk_start + 500]
        session.execute(delete(Measurement).where(Measurement.measurement_id.in_(chunk)))
    stale_runs = sorted(run_ids_in_db - new_run_ids)
    if stale_runs:
        session.execute(delete(ExperimentalRun).where(ExperimentalRun.run_id.in_(stale_runs)))
    session.flush()

    # Pull the surviving rows into the identity map in two queries, so merge() below does not issue
    # one SELECT per row (2,466 cells for PSI-69). The identity map holds objects weakly, so these
    # lists keep strong references until the merges are done.
    loaded_runs = session.scalars(
        select(ExperimentalRun).where(ExperimentalRun.investigation_id == investigation_id)
    ).all()
    loaded_measurements = session.scalars(
        select(Measurement)
        .join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id)
        .where(ExperimentalRun.investigation_id == investigation_id)
    ).all()
    existing_runs = {r.run_id for r in loaded_runs}
    existing_measurements = {m.measurement_id for m in loaded_measurements}

    # Existing rows: merge (served from the identity map). New rows: add (batched INSERTs).
    for r in bundle.runs:
        if r["run_id"] in existing_runs:
            session.merge(ExperimentalRun(**r))
        else:
            session.add(ExperimentalRun(**r))
    session.flush()
    for m in bundle.measurements:
        if m["measurement_id"] in existing_measurements:
            session.merge(Measurement(**m))
        else:
            session.add(Measurement(**m))
    session.flush()

    session.execute(
        delete(DataQualityCheck).where(DataQualityCheck.extraction_run_id == er["extraction_run_id"])
    )
    for c in bundle.checks:
        session.add(
            DataQualityCheck(
                check_id=ids.quality_check_id(er["extraction_run_id"], c.check_name),
                extraction_run_id=er["extraction_run_id"],
                check_name=c.check_name,
                severity=c.severity.value,
                outcome=c.outcome.value,
                affected_count=c.affected_count,
                description=c.description,
                details_json=_jsonable(c.details),
            )
        )
    session.flush()
    return len(stale_runs), len(stale_measurements)


def _withdraw_loaded_source(session: Session, source: SourceRecord) -> int:
    """A source loaded earlier and later QUARANTINED (or otherwise not usable) must stop feeding analysis/RAG.

    Rows are kept for audit (never silently deleted); the investigation records the new registry status and
    every measurement becomes usable_for_analysis = false with a ``source_withdrawn`` flag. A later load of
    the same source once it is ACQUIRED/VERIFIED again recomputes both from the source bytes.
    """
    investigation = session.get(Investigation, source.source_id)
    if investigation is None:
        return 0
    investigation.registry_status = source.verification_status.value
    measurements = session.scalars(
        select(Measurement)
        .join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id)
        .where(ExperimentalRun.investigation_id == source.source_id)
    ).all()
    for m in measurements:
        m.usable_for_analysis = False
        if "source_withdrawn" not in m.quality_flags:
            m.quality_flags = sorted([*m.quality_flags, "source_withdrawn"])
    session.flush()
    return len(measurements)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


def load_all(
    session: Session,
    root: Path,
    source_ids: list[str] | None = None,
    *,
    check_schema: bool = True,
) -> LoadReport:
    """Load every registry source that has an extractor (or the requested ones) in one transaction."""
    if check_schema:
        assert_schema_at_head(session)
    registry = load_registry(registry_path(root))
    policy = EligibilityPolicy(root)  # scientific evidence decisions (data/metadata/source_eligibility.csv)
    wanted = source_ids or [r.source_id for r in registry if r.source_type.startswith("NASA_PSI")]
    revision = git_revision(root)
    results: list[SourceLoadResult] = []

    with session.begin():
        seed_vocabulary(session)
        for sid in wanted:
            source: SourceRecord | None = find_source(registry, sid)
            if source is None:
                results.append(SourceLoadResult(sid, False, "not in source_registry.csv"))
                continue
            if not source.usable_as_evidence:
                withdrawn = _withdraw_loaded_source(session, source)
                reason = f"{source.verification_status.value} in source_registry.csv; refused"
                if withdrawn:
                    reason += f"; {withdrawn} previously loaded measurements withdrawn from analysis"
                results.append(SourceLoadResult(sid, False, reason))
                continue
            decision = policy.decision(sid)
            if not decision.usable_as_evidence:
                # e.g. PSI-25: ACQUIRED in the registry but ACQUIRED_BUT_EXCLUDED by the scientific owner.
                # Refused even if an extractor exists; anything loaded earlier is withdrawn from analysis.
                withdrawn = _withdraw_loaded_source(session, source)
                reason = f"{decision.eligibility.value} in source_eligibility.csv; refused"
                if withdrawn:
                    reason += f"; {withdrawn} previously loaded measurements withdrawn from analysis"
                results.append(SourceLoadResult(sid, False, reason))
                continue
            module = EXTRACTORS.get(sid)
            if module is None:
                results.append(SourceLoadResult(sid, False, NOT_LOADED_REASONS.get(sid, "no extractor")))
                continue
            bundle = module.extract(root, source, manifest_path(root), code_revision=revision)
            deleted_runs, deleted_measurements = _load_bundle(session, bundle)
            results.append(
                SourceLoadResult(
                    sid,
                    True,
                    runs=len(bundle.runs),
                    measurements=len(bundle.measurements),
                    deleted_runs=deleted_runs,
                    deleted_measurements=deleted_measurements,
                    warnings=[
                        f"{c.check_name}: {c.affected_count}"
                        for c in bundle.checks
                        if c.outcome.value == "flagged"
                    ],
                    extraction_run_id=str(bundle.extraction_run["extraction_run_id"]),
                )
            )
    return LoadReport(results)
