"""Typed contracts for the Research Orchestrator (no LangGraph import here).

Two concepts are deliberately separate:
* evidence class (OBSERVED / MODELLED / ILLUSTRATIVE): how a result was produced.
* scientific eligibility (formal evidence vs exploratory use): whether a source may be used, and how.
ResearchRun, DatasetRelease and EligibilitySnapshot are logical contracts here; no database schema is implied.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_PLAN_STEPS = 8


class EvidenceClass(str, Enum):
    OBSERVED = "OBSERVED"  # NASA-reported values or verbatim source text
    MODELLED = "MODELLED"  # output of a registered deterministic method
    ILLUSTRATIVE = "ILLUSTRATIVE"  # schematic, never a measurement


class PermissionTier(str, Enum):
    T0_READ = "T0_READ"  # read eligible data
    T1_COMPUTE = "T1_COMPUTE"  # deterministic computation
    T2_APPROVAL = "T2_APPROVAL"  # sensitive or expensive: waits for explicit human approval


class SourceUse(BaseModel):
    """Scientific eligibility of one source, kept apart from evidence class."""

    source_id: str
    eligibility: str
    formal_evidence: bool  # only VERIFIED_ELIGIBLE; PENDING_VERIFICATION never qualifies
    exploratory_use: bool  # may be used, labelled exploratory
    reason: str = ""
    decided_on: str = ""


class EligibilitySnapshot(BaseModel):
    """Immutable copy of the decisions in effect for one run (logical contract)."""

    model_config = ConfigDict(frozen=True)
    sources: dict[str, SourceUse]
    snapshot_hash: str


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(pattern=r"^s[0-9]{1,2}$")
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    purpose: str = Field(default="", max_length=300)


class ResearchPlan(BaseModel):
    """Typed, bounded plan. Proposed by a planner; validated against the allowlist before use."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=2000)
    steps: list[PlanStep] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)
    planner: str = "offline"


class Provenance(BaseModel):
    tool: str
    tool_version: str
    input_sha256: str
    output_sha256: str | None = None
    eligibility_snapshot_hash: str


class StepResult(BaseModel):
    step_id: str
    tool: str
    tier: PermissionTier
    status: Literal["ok", "failed", "not_executed", "rejected"]
    evidence_class: EvidenceClass | None = None  # None for control decisions (eligibility, comparison gate)
    outputs: dict[str, Any] | None = None
    error: str | None = None
    provenance: Provenance | None = None
    uncertainty: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    evidence_class: EvidenceClass
    # "formal" only when every source behind the claim is VERIFIED_ELIGIBLE; otherwise "exploratory"
    evidence_tier: Literal["exploratory", "formal"] = "exploratory"
    sources: list[str] = Field(default_factory=list)
    step_id: str
    citations: list[str] = Field(default_factory=list)  # chunk keys, measurement ids or provenance routes


class ResearchReport(BaseModel):
    question: str
    status: Literal["completed", "abstained", "comparison_blocked", "awaiting_approval", "failed"]
    abstention_reason: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    eligibility: dict[str, SourceUse] = Field(default_factory=dict)
    eligibility_snapshot_hash: str = ""
    eligibility_snapshot_persistent: bool = False  # in-process only until a durable store is integrated
    plan: ResearchPlan | None = None
    steps: list[StepResult] = Field(default_factory=list)
    notice: str = (
        "Independent research prototype. Numbers come only from deterministic FlameScope services on "
        "eligible NASA evidence; PSI-69 is pending verification (exploratory, not approved)."
    )


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
