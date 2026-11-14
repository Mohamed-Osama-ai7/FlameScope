"""PostgreSQL integration (runs only when FLAMESCOPE_TEST_DATABASE_URL is set).

Safety: the tests never touch the database named in the URL. They create a throw-away database
``flamescope_test_<random>`` on the same server, use it, and drop it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.data_platform import loader
from app.data_platform.db import make_engine, session_factory
from app.data_platform.models import ExtractionRun, Measurement
from app.data_platform.schema_version import current_revision, expected_head

from .conftest import PROJECT_ROOT, RAW_PSI69, alembic_config


@pytest.fixture
def scratch_pg(pg_url: str) -> Iterator[str]:
    base = make_url(pg_url)
    name = f"flamescope_test_{uuid.uuid4().hex[:10]}"
    admin = make_engine(base.set(database="postgres").render_as_string(hide_password=False))
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_postgres_migration_has_no_drift_and_round_trips(scratch_pg):
    cfg = alembic_config(scratch_pg)
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if models and migrations disagree
    engine = make_engine(scratch_pg)
    assert current_revision(engine) == expected_head()
    with engine.connect() as conn:
        types = dict(
            conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'measurements' AND column_name IN ('quality_flags', 'measurement_id')"
                )
            ).all()
        )
    assert types == {"quality_flags": "jsonb", "measurement_id": "uuid"}
    engine.dispose()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.mark.skipif(not RAW_PSI69.exists(), reason="raw PSI-69 table not present (gitignored)")
def test_postgres_load_is_idempotent_and_jsonb_filters_work(scratch_pg):
    command.upgrade(alembic_config(scratch_pg), "head")
    engine = make_engine(scratch_pg)
    factory = session_factory(engine)
    for _ in range(2):
        with factory() as s:
            assert loader.load_all(s, PROJECT_ROOT, ["PSI-69"]).ok
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Measurement)) == 2466
        assert s.scalar(select(func.count()).select_from(ExtractionRun)) == 1
        flagged = s.scalar(
            text(
                "SELECT count(*) FROM measurements "
                "WHERE quality_flags @> '[\"invalid_nonpositive_pressure\"]'"
            )
        )
        assert flagged == 1
    engine.dispose()
