"""Runtime configuration from environment variables (12-factor; no secrets in code)."""

from __future__ import annotations

import os
from pathlib import Path

DATABASE_URL_ENV = "FLAMESCOPE_DATABASE_URL"
DATA_ROOT_ENV = "FLAMESCOPE_PROJECT_ROOT"

# backend/app/data_platform/settings.py -> parents[3] = repository root (same rule as app/api/routes.py)
_DEFAULT_ROOT = Path(__file__).resolve().parents[3]


def database_url() -> str | None:
    """SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db. None = no database configured."""
    value = os.environ.get(DATABASE_URL_ENV, "").strip()
    return value or None


def project_root() -> Path:
    value = os.environ.get(DATA_ROOT_ENV, "").strip()
    return Path(value).resolve() if value else _DEFAULT_ROOT


def registry_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "data" / "metadata" / "source_registry.csv"


def manifest_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "data" / "metadata" / "artifact_manifest.csv"
