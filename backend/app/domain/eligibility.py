"""Evidence eligibility: which sources may support a Copilot answer, and why the others may not.

Base truth is the shared source registry (data/metadata/source_registry.csv, also read by the Data
Platform). `data/metadata/source_eligibility.csv` records the scientific owner's evidence decisions. It can
only RESTRICT what the registry allows; it can never promote a source:

* not in the registry                       -> UNREGISTERED, unusable
* registry QUARANTINED                      -> QUARANTINED, unusable
* registry status not usable (not acquired) -> PENDING_VERIFICATION, unusable
* registry ACQUIRED/VERIFIED, no decision   -> PENDING_VERIFICATION, unusable (default deny)
* registry ACQUIRED/VERIFIED with decision  -> the decision; VERIFIED_ELIGIBLE needs registry VERIFIED

Changing a decision is the scientific owner's call (docs/14 section 2); this module never edits either file.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.domain.sources import SourceRecord, VerificationStatus, load_registry


class Eligibility(str, Enum):
    VERIFIED_ELIGIBLE = "VERIFIED_ELIGIBLE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACQUIRED_BUT_EXCLUDED = "ACQUIRED_BUT_EXCLUDED"
    QUARANTINED = "QUARANTINED"
    UNREGISTERED = "UNREGISTERED"


USABLE_ELIGIBILITY = {Eligibility.VERIFIED_ELIGIBLE, Eligibility.PENDING_VERIFICATION}


@dataclass(frozen=True)
class SourceDecision:
    source_id: str
    eligibility: Eligibility
    usable_as_evidence: bool
    registry_status: str  # "" when the source is not registered
    reason: str
    decision_owner: str = ""
    decided_on: str = ""


def registry_path(root: Path) -> Path:
    return root / "data/metadata/source_registry.csv"


def decisions_path(root: Path) -> Path:
    return root / "data/metadata/source_eligibility.csv"


def _read_decisions(root: Path) -> dict[str, dict[str, str]]:
    p = decisions_path(root)
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8", newline="") as fh:
        return {r["source_id"]: r for r in csv.DictReader(fh)}


def resolve(
    source_id: str, registry: dict[str, SourceRecord], rows: dict[str, dict[str, str]]
) -> SourceDecision:
    row = rows.get(source_id) or {}
    owner, on, why = row.get("decision_owner", ""), row.get("decided_on", ""), row.get("reason", "")
    src = registry.get(source_id)
    if src is None:
        return SourceDecision(
            source_id, Eligibility.UNREGISTERED, False, "", why or "not in the source registry", owner, on
        )
    status = src.verification_status.value
    if src.verification_status is VerificationStatus.QUARANTINED:
        return SourceDecision(
            source_id, Eligibility.QUARANTINED, False, status, why or "registry status QUARANTINED", owner, on
        )
    if not src.usable_as_evidence:
        return SourceDecision(
            source_id,
            Eligibility.PENDING_VERIFICATION,
            False,
            status,
            why or f"registry status {status}",
            owner,
            on,
        )
    if not row:
        return SourceDecision(
            source_id,
            Eligibility.PENDING_VERIFICATION,
            False,
            status,
            "no evidence decision recorded",
            owner,
            on,
        )
    try:
        elig = Eligibility(row["eligibility"].strip())
    except ValueError:
        return SourceDecision(
            source_id,
            Eligibility.PENDING_VERIFICATION,
            False,
            status,
            f"unknown eligibility '{row['eligibility']}'",
        )
    if elig is Eligibility.VERIFIED_ELIGIBLE and src.verification_status is not VerificationStatus.VERIFIED:
        elig = Eligibility.PENDING_VERIFICATION  # a decision file cannot promote past the registry
    usable = row.get("usable_as_evidence", "").strip().lower() == "yes" and elig in USABLE_ELIGIBILITY
    return SourceDecision(source_id, elig, usable, status, why, owner, on)


class EligibilityPolicy:
    def __init__(self, root: Path) -> None:
        self.registry = {r.source_id: r for r in load_registry(registry_path(root))}
        self.rows = _read_decisions(root)
        self._cache: dict[str, SourceDecision] = {}

    def decision(self, source_id: str) -> SourceDecision:
        if source_id not in self._cache:
            self._cache[source_id] = resolve(source_id, self.registry, self.rows)
        return self._cache[source_id]

    def all_decisions(self) -> list[SourceDecision]:
        ids = sorted(set(self.registry) | set(self.rows))
        return [self.decision(s) for s in ids]


def explicit_exclusion(root: Path, source_id: str) -> str | None:
    """Eligibility value when source_eligibility.csv explicitly marks a source unusable, else None.

    For code paths that only hold one SourceRecord (e.g. an extractor): an explicit "no" always refuses;
    the full default-deny policy (EligibilityPolicy) is applied by the loader and the APIs.
    """
    row = _read_decisions(root).get(source_id)
    if row and row.get("usable_as_evidence", "").strip().lower() != "yes":
        return row.get("eligibility", "EXCLUDED").strip() or "EXCLUDED"
    return None
