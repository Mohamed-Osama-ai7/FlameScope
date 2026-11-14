"""Alembic revision helpers shared by the loader and the status endpoint."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@lru_cache(maxsize=1)
def expected_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if head is None:
        raise RuntimeError("no Alembic head revision found")
    return head


def current_revision(engine: Engine) -> str | None:
    """Revision stamped in the database, or None if the alembic_version table is absent.

    Connection errors propagate (the caller decides whether the database is reachable).
    """
    with engine.connect() as conn:
        try:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except ProgrammingError:  # table does not exist yet
            return None
        except OperationalError as exc:  # SQLite reports a missing table as OperationalError
            if "no such table" in str(exc):
                return None
            raise
