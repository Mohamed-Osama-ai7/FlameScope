"""Typed source-registry contract.

The registry CSV is the single source of truth for which NASA resources are recorded. Status flags
exposed by the API are *derived* from it, never hard-coded, so the UI cannot claim a resource is
recorded (or not) independently of the registry.
"""
from __future__ import annotations

import csv
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerificationStatus(str, Enum):
    NOT_YET_ACQUIRED = "NOT_YET_ACQUIRED"
    CANDIDATE_ONLY = "CANDIDATE_ONLY"
    ACQUIRED = "ACQUIRED"  # bytes downloaded, hashed and licensed; content not yet reviewed
    VERIFIED = "VERIFIED"  # content reviewed by a named team member against the source
    QUARANTINED = "QUARANTINED"  # known metadata conflict; must not feed scientific analysis


class SourceRecord(BaseModel):
    source_id: str = Field(min_length=1)
    source_title: str
    source_type: str
    official_challenge_resource: bool
    source_url: str = ""
    doi: str = ""
    version_or_release: str = ""
    retrieved_at_utc: str = ""
    license: str = ""
    raw_file_path: str = ""
    sha256: str = ""
    verification_status: VerificationStatus
    notes: str = ""

    @field_validator("official_challenge_resource", mode="before")
    @classmethod
    def _yes_no(cls, value: object) -> object:
        if isinstance(value, str):
            v = value.strip().upper()
            if v in {"YES", "NO"}:
                return v == "YES"
            raise ValueError("official_challenge_resource must be YES or NO")
        return value

    @model_validator(mode="after")
    def _acquired_needs_provenance(self) -> SourceRecord:
        if self.verification_status in (VerificationStatus.ACQUIRED, VerificationStatus.VERIFIED):
            missing = [
                name
                for name in ("source_url", "retrieved_at_utc", "license", "raw_file_path")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"{self.source_id}: status {self.verification_status.value} requires "
                    + ", ".join(missing)
                )
            if not _SHA256.match(self.sha256):
                raise ValueError(f"{self.source_id}: sha256 must be 64 lowercase hex characters")
        return self

    @property
    def usable_as_evidence(self) -> bool:
        return self.verification_status in (VerificationStatus.ACQUIRED, VerificationStatus.VERIFIED)


class RegistryError(RuntimeError):
    pass


def load_registry(path: Path) -> list[SourceRecord]:
    if not path.exists():
        raise RegistryError(f"Source registry not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records: list[SourceRecord] = []
    seen: set[str] = set()
    for row in rows:
        record = SourceRecord.model_validate({k: (v or "").strip() for k, v in row.items()})
        if record.source_id in seen:
            raise RegistryError(f"Duplicate source_id: {record.source_id}")
        seen.add(record.source_id)
        records.append(record)
    return records


def find_source(records: list[SourceRecord], source_id: str) -> SourceRecord | None:
    return next((r for r in records if r.source_id == source_id), None)


def official_resource_recorded(records: list[SourceRecord]) -> bool:
    """True only when an official challenge resource has actually been acquired and hashed."""
    return any(r.official_challenge_resource and r.usable_as_evidence for r in records)
