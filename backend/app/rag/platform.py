"""Bridge to the Scientific Data Platform (branch feat/scientific-data-platform, contract 1.0).

The platform package is optional at import time so this branch runs on its own. When the package is
importable AND FLAMESCOPE_DATABASE_URL is set, every measurement the Copilot cites is checked against the
database as the contract requires (docs/15 B.5): the measurement exists; its evidence status agrees
(usable value / invalid value / missing cell); a stated value and unit equal the database; the
investigation's registry status is ACQUIRED or VERIFIED. If the database is configured but cannot be read,
numeric claims are withdrawn (contract B.4: never answer numerically without the database).

`sync_document_chunks` writes eligible chunks into the platform table `document_chunks` with the same
UUIDs as the in-memory index (app/rag/ids.py); it never writes ineligible chunks, because that table has
no eligibility column and anything stored there would look usable to other consumers.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.rag.measurements import EvidenceStatus
from app.rag.schemas import Chunk, MeasurementRef

USABLE_REGISTRY = {"ACQUIRED", "VERIFIED"}


@dataclass
class Verification:
    mode: str  # "platform" | "loader_fallback" | "unavailable"
    detail: str
    problems: dict[str, list[str]] = field(default_factory=dict)  # measurement_id -> problems


def _platform() -> tuple[Any, Any, str]:
    """(engine, models, reason). engine is None when the platform is not usable from this process."""
    try:
        from app.data_platform import models  # type: ignore[import-not-found,unused-ignore]
        from app.data_platform.db import get_engine  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None, None, "Data Platform package not present in this checkout"
    if not os.environ.get("FLAMESCOPE_DATABASE_URL", "").strip():
        return None, None, "FLAMESCOPE_DATABASE_URL is not set"
    try:
        return get_engine(), models, ""
    except Exception as exc:  # noqa: BLE001 - any engine error means "unavailable", reported as such
        return False, None, f"Data Platform database unavailable: {type(exc).__name__}"


def platform_state() -> dict[str, object]:
    engine, _, reason = _platform()
    return {"connected": bool(engine), "reason": reason or "configured"}


def _check(m: MeasurementRef, row: Any, registry_status: str) -> list[str]:
    status = EvidenceStatus(m.evidence_status)
    out: list[str] = []
    if registry_status not in USABLE_REGISTRY:
        out.append(f"investigation registry status is {registry_status}")
    if status in (EvidenceStatus.CLEAN, EvidenceStatus.QUALIFIED):
        if not row.usable_for_analysis:
            out.append("database says not usable_for_analysis")
        if row.value is None or m.value is None or abs(float(row.value) - float(m.value)) > 1e-12:
            out.append(f"value differs (database {row.value}, cited {m.value})")
        if row.unit != m.unit:
            out.append(f"unit differs (database {row.unit}, cited {m.unit})")
    elif status is EvidenceStatus.INVALID:
        if row.usable_for_analysis:
            out.append("cited as invalid but the database marks it usable")
    elif status is EvidenceStatus.MISSING and row.value is not None:
        out.append("cited as missing but the database holds a value")
    return out


def verify(refs: list[MeasurementRef]) -> Verification:
    if not refs:
        return Verification("platform", "no measurements cited")
    engine, models, reason = _platform()
    if engine is None:
        return Verification(
            "loader_fallback",
            f"{reason}; measurement ids follow the platform contract but were not checked against "
            "its database",
        )
    if engine is False:
        return Verification("unavailable", reason, {m.measurement_id: [reason] for m in refs})
    from sqlalchemy.orm import Session

    problems: dict[str, list[str]] = {}
    try:
        with Session(engine) as s:
            for m in refs:
                row = s.get(models.Measurement, uuid.UUID(m.measurement_id))
                if row is None:
                    problems[m.measurement_id] = ["measurement_id not found in the Data Platform"]
                    continue
                run = s.get(models.ExperimentalRun, row.run_id)
                inv = s.get(models.Investigation, run.investigation_id) if run else None
                p = _check(m, row, inv.registry_status if inv else "unknown")
                if p:
                    problems[m.measurement_id] = p
    except Exception as exc:  # noqa: BLE001
        why = f"Data Platform database unavailable: {type(exc).__name__}"
        return Verification("unavailable", why, {m.measurement_id: [why] for m in refs})
    return Verification("platform", "checked against the Data Platform database (contract B.5)", problems)


def sync_document_chunks(chunks: list[Chunk], engine: Any = None) -> dict[str, int]:
    """Upsert eligible chunks into document_chunks. Idempotent (deterministic UUIDs)."""
    from sqlalchemy.orm import Session

    from app.data_platform import models  # type: ignore[import-not-found,unused-ignore]

    if engine is None:
        engine, _, reason = _platform()
        if not engine:
            raise RuntimeError(reason)
    stats = {"written": 0, "skipped_ineligible": 0, "skipped_artifact_not_in_platform": 0}
    with Session(engine) as s:
        known_artifacts = {str(a) for (a,) in s.query(models.SourceArtifact.artifact_id).all()}
        known_inv = {i for (i,) in s.query(models.Investigation.investigation_id).all()}
        for c in chunks:
            if not c.usable_as_evidence:
                stats["skipped_ineligible"] += 1
                continue
            if c.artifact_id not in known_artifacts:
                stats["skipped_artifact_not_in_platform"] += 1
                continue
            s.merge(
                models.DocumentChunk(
                    chunk_id=uuid.UUID(c.chunk_id),
                    artifact_id=uuid.UUID(c.artifact_id),
                    investigation_id=c.source_id if c.source_id in known_inv else None,
                    combustion_regime=c.regime,
                    page_or_section=c.locator_text,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    chunker_version=c.chunker_version,
                )
            )
            stats["written"] += 1
        s.commit()
    return stats
