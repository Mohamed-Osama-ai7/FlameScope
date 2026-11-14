"""Alembic environment for the FlameScope scientific database.

URL resolution order: an open connection passed in ``config.attributes["connection"]`` (tests) ->
``sqlalchemy.url`` set on the Config (e.g. ``-x``/programmatic) -> FLAMESCOPE_DATABASE_URL.
Offline mode (``alembic upgrade head --sql``) renders PostgreSQL DDL without a database.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.data_platform.models import Base
from app.data_platform.settings import DATABASE_URL_ENV, database_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or database_url()
    if not url:
        if context.is_offline_mode():
            return "postgresql+psycopg://offline/flamescope"
        raise RuntimeError(
            f"Set {DATABASE_URL_ENV} (e.g. postgresql+psycopg://user:pass@localhost:5432/flamescope)"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _run(conn)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs batch ALTERs
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
