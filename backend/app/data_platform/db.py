"""Engine and session management.

The engine is created lazily so importing the API never requires a database. Endpoints that need the
database get a session through ``get_session``; when no database is configured they answer 503 with an
explicit message instead of returning empty or invented data.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.data_platform.settings import DATABASE_URL_ENV, database_url


class DatabaseNotConfigured(RuntimeError):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs unless asked
            cur.close()

        return engine
    connect_args = {"connect_timeout": 5} if url.startswith("postgresql") else {}
    return create_engine(
        url, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args=connect_args
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = database_url()
    if url is None:
        raise DatabaseNotConfigured(f"{DATABASE_URL_ENV} is not set")
    return make_engine(url)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency (read-only use). Tests override it via app.dependency_overrides."""
    try:
        engine = get_engine()
    except DatabaseNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Scientific database not configured ({exc}). Start it with `docker compose up` "
                "and load data with `python scripts/load_database.py`."
            ),
        ) from exc
    with session_factory(engine)() as session:
        try:
            yield session
        except OperationalError as exc:  # configured but down/unreachable: explicit 503, not a bare 500
            raise HTTPException(
                status_code=503,
                detail=f"Scientific database unreachable ({type(exc).__name__}). Check `docker compose ps`.",
            ) from exc
