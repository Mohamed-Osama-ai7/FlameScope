"""Evidence status of the sources behind Flame Vision outputs (PSI-69 today: PENDING_VERIFICATION).

The vision manifest (data/metadata/vision_artifact_manifest.csv) lists two kinds of rows:

* data rows (camera settings, frame index, frames, test log): the evidence the results are derived from;
* ``reference_report`` rows: a published report used only for a labelled, exploratory cross-check
  (NASA/TP-2015-216046, UNREGISTERED). It is never an input of the K/D0^2 results.

Their status comes from the central policy in app/domain/eligibility.py (registry status AND
source_eligibility.csv). Nothing here decides eligibility.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.domain.eligibility import EligibilityPolicy

REFERENCE_ROLE = "reference_report"


def _rows(root: Path) -> list[dict[str, str]]:
    path = root / "data" / "metadata" / "vision_artifact_manifest.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("source_id")]


def vision_source_ids(root: Path) -> list[str]:
    """Sources the vision results are derived from (reference reports excluded)."""
    return sorted({r["source_id"] for r in _rows(root) if r.get("role") != REFERENCE_ROLE})


def reference_source_ids(root: Path) -> list[str]:
    """Published reports used only for the exploratory cross-check."""
    return sorted({r["source_id"] for r in _rows(root) if r.get("role") == REFERENCE_ROLE})


def evidence_eligibility(root: Path) -> dict[str, str]:
    """{source_id: eligibility} for the sources the vision results are derived from."""
    policy = EligibilityPolicy(root)
    return {sid: policy.decision(sid).eligibility.value for sid in vision_source_ids(root)}


def reference_eligibility(root: Path) -> dict[str, str]:
    """{source_id: eligibility} for the cross-check reference (UNREGISTERED today: never evidence)."""
    policy = EligibilityPolicy(root)
    return {sid: policy.decision(sid).eligibility.value for sid in reference_source_ids(root)}
