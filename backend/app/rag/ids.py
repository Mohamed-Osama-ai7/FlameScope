"""Deterministic identifiers shared with the Scientific Data Platform.

The formulas are the Data Platform contract (branch feat/scientific-data-platform,
app/data_platform/ids.py, contract 1.0): same namespace, same input strings. They are restated here so
the RAG layer runs without the platform package, and `tests/test_rag_platform_parity.py` asserts that both
implementations return identical UUIDs whenever the platform package is importable. A chunk therefore has
the same id in the in-memory index and in the platform table `document_chunks`.
"""

from __future__ import annotations

import uuid

NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:flamescope:data-platform:v1")


def artifact_id(sha256: str, relative_path: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"artifact|{sha256}|{relative_path}"))


def measurement_id(artifact_sha256: str, source_row: int, source_column: str) -> str:
    return str(
        uuid.uuid5(NAMESPACE, f"measurement|{artifact_sha256}|row={source_row}|column={source_column}")
    )


def run_id(source_id: str, source_row: int) -> str:
    return f"{source_id}-r{source_row:03d}"


def chunk_id(artifact: str, chunker_version: str, chunk_index: int) -> str:
    """Key of `document_chunks` (unique on artifact_id, chunker_version, chunk_index)."""
    return str(uuid.uuid5(NAMESPACE, f"chunk|{artifact}|{chunker_version}|{chunk_index}"))
