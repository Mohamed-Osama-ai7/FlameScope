"""Loader + schema on SQLite (created by the real Alembic migration): idempotency, refusals, constraints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Engine, delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data_platform import loader
from app.data_platform.db import make_engine, session_factory
from app.data_platform.extract_flex import ExtractionRefused
from app.data_platform.models import (
    AnalysisResult,
    AnalysisResultInput,
    Base,
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

from .conftest import PROJECT_ROOT, alembic_config

DATA_TABLES = (Investigation, SourceArtifact, ExtractionRun, ExperimentalRun, Measurement, DataQualityCheck)


def snapshot(session: Session) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for model in (*DATA_TABLES, Variable, Unit):
        cols = [c.key for c in inspect(model).columns if c.key not in ("last_loaded_at", "code_revision")]
        pk = inspect(model).primary_key
        rows = session.execute(select(*[getattr(model, c) for c in cols]).order_by(*pk)).all()
        out[model.__tablename__] = [dict(zip(cols, r, strict=True)) for r in rows]
    return out


def test_migration_matches_models_and_downgrades(sqlite_url):
    cfg = alembic_config(sqlite_url)
    command.upgrade(cfg, "head")
    engine = make_engine(sqlite_url)
    assert current_revision(engine) == expected_head()
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        assert {c["name"] for c in inspect(engine).get_columns(name)} == {c.name for c in table.columns}, name
    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_load_refuses_when_schema_not_at_head(sqlite_url):
    engine = make_engine(sqlite_url)
    with session_factory(engine)() as s, pytest.raises(loader.SchemaNotReady):
        loader.load_all(s, PROJECT_ROOT)
    engine.dispose()


def test_load_is_complete_and_idempotent(loaded_sqlite: Engine):
    with session_factory(loaded_sqlite)() as s:
        first = snapshot(s)
        assert len(first["experimental_runs"]) == 274
        assert len(first["measurements"]) == 2466
        assert {r["investigation_id"] for r in first["investigations"]} == {"PSI-69"}
        er_before = s.scalars(select(ExtractionRun)).one()
    with session_factory(loaded_sqlite)() as s:
        report = loader.load_all(s, PROJECT_ROOT)
    assert report.ok
    psi69 = next(r for r in report.results if r.source_id == "PSI-69")
    assert (psi69.deleted_runs, psi69.deleted_measurements) == (0, 0)
    with session_factory(loaded_sqlite)() as s:
        assert snapshot(s) == first  # byte-for-byte identical rows after a reload
        er_after = s.scalars(select(ExtractionRun)).one()
        assert er_after.extraction_run_id == er_before.extraction_run_id
        assert er_after.first_loaded_at == er_before.first_loaded_at


def test_unsupported_and_quarantined_sources_are_reported_not_loaded(loaded_sqlite: Engine):
    with session_factory(loaded_sqlite)() as s:
        report = loader.load_all(s, PROJECT_ROOT, ["PSI-25", "PSI-98", "NOPE"])
    reasons = {r.source_id: (r.loaded, r.reason) for r in report.results}
    # PSI-25 is refused centrally by its evidence decision (before the missing-extractor check)
    assert reasons["PSI-25"][0] is False and "ACQUIRED_BUT_EXCLUDED" in reasons["PSI-25"][1]
    assert reasons["PSI-98"] == (False, "QUARANTINED in source_registry.csv; refused")
    assert reasons["NOPE"] == (False, "not in source_registry.csv")
    with session_factory(loaded_sqlite)() as s:
        assert s.scalar(select(func.count()).select_from(Investigation)) == 1


def test_refused_load_writes_nothing(migrated_sqlite: Engine, monkeypatch):
    def boom(*_a, **_k):
        raise ExtractionRefused("simulated integrity failure")

    monkeypatch.setattr(loader.extract_flex, "extract", boom)
    with session_factory(migrated_sqlite)() as s, pytest.raises(ExtractionRefused):
        loader.load_all(s, PROJECT_ROOT, ["PSI-69"])
    with session_factory(migrated_sqlite)() as s:
        for model in (*DATA_TABLES, Variable, Unit):
            assert s.scalar(select(func.count()).select_from(model)) == 0, model.__tablename__


def test_measurement_referenced_by_an_analysis_cannot_be_deleted(loaded_sqlite: Engine):
    with session_factory(loaded_sqlite)() as s:
        m = s.scalars(select(Measurement).order_by(Measurement.measurement_id).limit(1)).one()
        result = AnalysisResult(
            result_id=uuid.uuid4(),
            method_id="t",
            method_version="1",
            run_id=m.run_id,
            computable=False,
            abstention_reason="test",
            output_json={},
            created_at=datetime.now(UTC),
        )
        s.add(result)
        s.flush()
        s.add(AnalysisResultInput(result_id=result.result_id, measurement_id=m.measurement_id))
        s.commit()
        with pytest.raises(IntegrityError):
            s.execute(delete(Measurement).where(Measurement.measurement_id == m.measurement_id))
            s.flush()
        s.rollback()


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"value": None, "value_status": "parsed"}, "NULL value must be missing/unparseable"),
        ({"value": 1.0, "value_status": "missing"}, "a missing cell cannot carry a value"),
        ({"value": None, "value_status": "missing", "usable_for_analysis": True}, "usable needs a value"),
        ({"role": "result"}, "role vocabulary"),
        ({"unit": "furlong"}, "unit FK"),
        ({"variable_name": "made_up"}, "variable FK"),
        ({"uncertainty_value": -1.0}, "negative uncertainty"),
    ],
)
def test_database_rejects_invalid_measurements(loaded_sqlite: Engine, change, why):
    with session_factory(loaded_sqlite)() as s:
        base = s.scalars(select(Measurement).where(Measurement.value_status == "parsed").limit(1)).one()
        cols = {c.key: getattr(base, c.key) for c in inspect(Measurement).columns}
        cols.update(measurement_id=uuid.uuid4(), source_column=f"synthetic test column {why}")
        cols.update(change)
        s.add(Measurement(**cols))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()


def test_database_schema_sql_is_in_sync_with_migrations():
    """database/schema.sql is the offline rendering of the Alembic migrations (no hand edits)."""
    import io

    from alembic.config import Config

    from .conftest import BACKEND

    buf = io.StringIO()
    cfg = Config(str(BACKEND / "alembic.ini"), output_buffer=buf)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head", sql=True)

    def body(sql: str) -> list[str]:
        lines = [ln.rstrip() for ln in sql.splitlines()]
        return [ln for ln in lines if ln and not ln.startswith("-- ")]

    committed = (PROJECT_ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    assert body(committed) == body(buf.getvalue()), "regenerate database/schema.sql (see its header)"


def test_rows_dropped_by_a_new_source_version_are_removed(loaded_sqlite: Engine, monkeypatch):
    real_extract = loader.extract_flex.extract

    def without_last_run(*args, **kwargs):
        b = real_extract(*args, **kwargs)
        b.runs = [r for r in b.runs if r["run_id"] != "PSI-69-r274"]
        b.measurements = [m for m in b.measurements if m["run_id"] != "PSI-69-r274"]
        return b

    monkeypatch.setattr(loader.extract_flex, "extract", without_last_run)
    with session_factory(loaded_sqlite)() as s:
        report = loader.load_all(s, PROJECT_ROOT, ["PSI-69"])
    (res,) = report.results
    assert (res.runs, res.deleted_runs, res.deleted_measurements) == (273, 1, 9)
    with session_factory(loaded_sqlite)() as s:
        assert s.get(ExperimentalRun, "PSI-69-r274") is None
        assert s.scalar(select(func.count()).select_from(Measurement)) == 2466 - 9


def test_source_quarantined_after_loading_is_withdrawn_from_analysis(loaded_sqlite: Engine, monkeypatch):
    """Registry status wins over earlier loads: quarantined data stop feeding analysis and RAG.

    Rows are kept for audit; a reload once the source is usable again restores them.
    """
    from app.domain.sources import VerificationStatus

    real_registry = loader.load_registry

    def registry_with(status):
        def fake(path):
            return [
                r.model_copy(update={"verification_status": status}) if r.source_id == "PSI-69" else r
                for r in real_registry(path)
            ]

        return fake

    monkeypatch.setattr(loader, "load_registry", registry_with(VerificationStatus.QUARANTINED))
    with session_factory(loaded_sqlite)() as s:
        (res,) = loader.load_all(s, PROJECT_ROOT, ["PSI-69"]).results
    assert not res.loaded and "2466 previously loaded measurements withdrawn" in res.reason
    with session_factory(loaded_sqlite)() as s:
        assert s.get(Investigation, "PSI-69").registry_status == "QUARANTINED"
        assert (
            s.scalar(select(func.count()).select_from(Measurement).where(Measurement.usable_for_analysis))
            == 0
        )
        assert s.scalar(select(func.count()).select_from(Measurement)) == 2466  # kept for audit

    monkeypatch.setattr(loader, "load_registry", registry_with(VerificationStatus.ACQUIRED))
    with session_factory(loaded_sqlite)() as s:
        assert loader.load_all(s, PROJECT_ROOT, ["PSI-69"]).ok
    with session_factory(loaded_sqlite)() as s:
        assert s.get(Investigation, "PSI-69").registry_status == "ACQUIRED"
        usable = select(func.count()).select_from(Measurement).where(Measurement.usable_for_analysis)
        assert s.scalar(usable) == 2354
