"""Deterministic identifiers.

A reload of the same bytes with the same extractor version must produce the same primary keys, so
links held by the frontend, the RAG index or analysis results never break after a reload.
"""

from __future__ import annotations

import uuid

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:flamescope:data-platform:v1")


def artifact_id(sha256: str, relative_path: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"artifact|{sha256}|{relative_path}")


def extraction_run_id(extractor: str, version: str, input_digests: list[str]) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"extraction|{extractor}|{version}|{'|'.join(sorted(input_digests))}")


def measurement_id(artifact_sha256: str, source_row: int, source_column: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"measurement|{artifact_sha256}|row={source_row}|column={source_column}")


def quality_check_id(extraction_run: uuid.UUID, check_name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"quality|{extraction_run}|{check_name}")


def run_id(source_id: str, source_row: int) -> str:
    """Human-readable, URL-safe run key, e.g. PSI-69-r001.

    Keyed on the PSI row number, which is unique; FLEX identifiers are not (193F001 appears twice).
    """
    return f"{source_id}-r{source_row:03d}"
