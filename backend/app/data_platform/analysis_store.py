"""The only supported way to persist an analysis result.

The schema already links ``analysis_results`` to its inputs through ``analysis_result_inputs`` (FK,
ON DELETE RESTRICT), but a database constraint cannot require "at least one input" or "every input is
usable". This function enforces both before anything is written, so invalid, missing, withdrawn or
quarantined measurements cannot silently become inputs of a stored scientific result.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_platform.models import (
    AnalysisResult,
    AnalysisResultInput,
    ExperimentalRun,
    Investigation,
    Measurement,
)

USABLE_REGISTRY_STATUSES = frozenset({"ACQUIRED", "VERIFIED"})


class AnalysisInputRejected(ValueError):
    """Raised before any write; ``problems`` maps measurement id (or 'inputs') to the reason."""

    def __init__(self, problems: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in problems.items()))
        self.problems = problems


def record_analysis_result(
    session: Session,
    *,
    method_id: str,
    method_version: str,
    input_measurement_ids: list[uuid.UUID],
    output: dict[str, Any],
    computable: bool,
    abstention_reason: str | None = None,
    run_id: str | None = None,
) -> AnalysisResult:
    """Validate inputs, then add the result and its input links to the session (caller commits)."""
    ids = list(dict.fromkeys(input_measurement_ids))  # de-duplicate, keep order
    if not ids:
        raise AnalysisInputRejected({"inputs": "an analysis result needs at least one input measurement"})
    if not computable and not abstention_reason:
        raise AnalysisInputRejected({"inputs": "computable=false requires an abstention_reason"})

    rows = session.execute(
        select(Measurement, Investigation.registry_status)
        .join(ExperimentalRun, Measurement.run_id == ExperimentalRun.run_id)
        .join(Investigation, ExperimentalRun.investigation_id == Investigation.investigation_id)
        .where(Measurement.measurement_id.in_(ids))
    ).all()
    found = {m.measurement_id: (m, status) for m, status in rows}
    problems: dict[str, str] = {}
    for mid in ids:
        if mid not in found:
            problems[str(mid)] = "unknown measurement"
            continue
        m, status = found[mid]
        if status not in USABLE_REGISTRY_STATUSES:
            problems[str(mid)] = f"source registry status {status} (withdrawn or quarantined)"
        elif m.value is None:
            problems[str(mid)] = f"no numeric value (value_status={m.value_status})"
        elif not m.usable_for_analysis:
            problems[str(mid)] = f"not usable for analysis (flags: {', '.join(m.quality_flags) or 'none'})"
    if problems:
        raise AnalysisInputRejected(problems)

    result = AnalysisResult(
        result_id=uuid.uuid4(),
        method_id=method_id,
        method_version=method_version,
        run_id=run_id,
        computable=computable,
        abstention_reason=abstention_reason,
        output_json=output,
    )
    session.add(result)
    session.flush()
    session.add_all(AnalysisResultInput(result_id=result.result_id, measurement_id=mid) for mid in ids)
    session.flush()
    return result
