"""Fixtures for the scientific data platform tests.

Layers:
* no database      - always run
* SQLite (tmp file) - always run; schema created by the real Alembic migration
* PostgreSQL       - run only when FLAMESCOPE_TEST_DATABASE_URL is set (see docs/14)
Tests that need the raw PSI-69 file skip when it is absent (data/raw is gitignored), like the
existing suite; fetch it with: python backend/scripts/fetch_psi_table.py PSI-69 --root .
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.data_platform.db import get_engine, make_engine, session_factory
from app.data_platform.settings import DATABASE_URL_ENV

BACKEND = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND.parent
RAW_PSI69 = (
    PROJECT_ROOT / "data" / "raw" / "PSI-69" / "experimental_table" / "PSI-69_Experimental table_FLEX.csv"
)
PG_URL_ENV = "FLAMESCOPE_TEST_DATABASE_URL"

needs_raw = pytest.mark.skipif(not RAW_PSI69.exists(), reason="raw PSI-69 table not present (gitignored)")


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(autouse=True)
def _no_ambient_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never touch a developer's configured database by accident."""
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'flamescope_test.db').as_posix()}"


@pytest.fixture
def migrated_sqlite(sqlite_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(sqlite_url), "head")
    engine = make_engine(sqlite_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_sqlite: Engine) -> Iterator[Session]:
    with session_factory(migrated_sqlite)() as s:
        yield s


@pytest.fixture
def loaded_sqlite(migrated_sqlite: Engine) -> Engine:
    from app.data_platform.loader import load_all

    if not RAW_PSI69.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    with session_factory(migrated_sqlite)() as s:
        report = load_all(s, PROJECT_ROOT)
    assert report.ok
    return migrated_sqlite


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get(PG_URL_ENV, "").strip()
    if not url:
        pytest.skip(f"{PG_URL_ENV} not set (PostgreSQL integration tests)")
    return url


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_client(loaded_sqlite: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """API client backed by the loaded SQLite database (sessions and status both point at it)."""
    from app.data_platform import api as dp_api
    from app.data_platform.db import get_session
    from app.main import app

    factory = session_factory(loaded_sqlite)

    def override() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    monkeypatch.setattr(dp_api, "get_engine", lambda: loaded_sqlite)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)
