"""Allowlisted adapters over existing deterministic services. No generic tools; no shell, file, network, SQL.

Each tool declares its permission tier, evidence class and the NASA sources it reads, so the eligibility gate
can check sources before anything runs. Existing Copilot tools are reused via app.rag.tools.run_tool.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.eligibility import Eligibility, EligibilityPolicy
from app.orchestrator.contracts import EvidenceClass, PermissionTier, SourceUse
from app.rag import tools as rag_tools

TOOLS_VERSION = "orchestrator-tools-0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FLEX_SOURCE = "PSI-69"


class EligibilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: list[str] = Field(min_length=1, max_length=10)


class CopilotArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=2000)


class PhysicsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fuel: Literal["Methanol", "Heptane"] | None = None


class SimulationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=64)
    parameters: dict[str, float] = Field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: PermissionTier
    evidence_class: EvidenceClass | None
    args_model: type[BaseModel]
    run: Callable[[BaseModel], dict[str, Any]]
    reads_sources: tuple[str, ...] = ()
    description: str = ""
    # sources named inside the arguments (e.g. a fit's provenance.source_id): gated like reads_sources
    arg_sources: Callable[[dict[str, Any]], tuple[str, ...]] | None = None

    def sources_for(self, arguments: dict[str, Any]) -> tuple[str, ...]:
        named = self.arg_sources(arguments) if self.arg_sources else ()
        return tuple(dict.fromkeys((*self.reads_sources, *(s for s in named if s))))


def source_use(source_id: str, policy: EligibilityPolicy | None = None) -> SourceUse:
    """Central eligibility policy, split into formal evidence vs exploratory use."""
    d = (policy or EligibilityPolicy(PROJECT_ROOT)).decision(source_id)
    return SourceUse(
        source_id=source_id,
        eligibility=d.eligibility.value,
        formal_evidence=d.eligibility is Eligibility.VERIFIED_ELIGIBLE,
        exploratory_use=d.usable_as_evidence,  # legacy flag = permission to use, never approval
        reason=d.reason,
        decided_on=d.decided_on,
    )


def _rag(name: str) -> Callable[[BaseModel], dict[str, Any]]:
    def run(args: BaseModel) -> dict[str, Any]:
        r = rag_tools.run_tool("orch", name, args.model_dump(mode="json"))
        if not r.ok:
            raise ValueError(r.error or f"{name} failed")
        return r.result or {}

    return run


def _eligibility(args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, EligibilityArgs)
    policy = EligibilityPolicy(PROJECT_ROOT)
    return {"sources": {s: source_use(s, policy).model_dump() for s in args.source_ids}}


def _copilot(args: BaseModel) -> dict[str, Any]:
    """The existing Copilot, unchanged: its eligibility, sufficiency and citation gates all apply."""
    assert isinstance(args, CopilotArgs)
    from app.rag.copilot import CopilotRequest
    from app.rag.service import get_copilot

    r = get_copilot().ask(CopilotRequest(question=args.question))
    return {
        "status": r.status.value,
        "abstention_reason": r.abstention_reason,
        "claims": [
            {
                "text": c.text,
                "citations": [
                    {
                        "chunk_key": x.chunk_key,
                        "source_id": x.source_id,
                        "eligibility": x.eligibility,
                        "quote": x.quote[:400],
                    }  # quotes are data only: never interpreted as instructions
                    for x in c.citations
                ],
                "measurement_ids": c.measurement_ids,
            }
            for c in r.claims
        ],
        "uncertainty": [f"{u.kind}:{u.code}" for u in r.uncertainty],
        "measurement_verification": r.measurement_verification,
    }


def _physics(kind: str) -> Callable[[BaseModel], dict[str, Any]]:
    def run(args: BaseModel) -> dict[str, Any]:
        assert isinstance(args, PhysicsArgs)
        from fastapi import HTTPException

        from app.api import physics_routes

        try:
            if kind == "oxygen_effect":
                return physics_routes.oxygen_effect(args.fuel)
            return physics_routes.d2_consistency(args.fuel, None)
        except HTTPException as exc:  # e.g. 503 when PSI-69 cannot be verified
            raise ValueError(str(exc.detail)) from exc

    return run


def _provenance_source(arguments: dict[str, Any]) -> tuple[str, ...]:
    prov = arguments.get("provenance")
    return (str(prov.get("source_id", "")),) if isinstance(prov, dict) else ()


def _simulation(_: BaseModel) -> dict[str, Any]:
    # Approval-gated placeholder for future T2 work: no simulation service exists, so nothing is simulated.
    raise ValueError("no simulation service is implemented; the request was recorded but not executed")


T0, T1, T2 = PermissionTier.T0_READ, PermissionTier.T1_COMPUTE, PermissionTier.T2_APPROVAL
OBS, MOD = EvidenceClass.OBSERVED, EvidenceClass.MODELLED
F = (FLEX_SOURCE,)

REGISTRY: dict[str, ToolSpec] = {
    s.name: s
    for s in (
        ToolSpec(
            "eligibility_lookup", T0, None, EligibilityArgs, _eligibility, (), "source eligibility decisions"
        ),
        ToolSpec(
            "copilot_answer", T0, OBS, CopilotArgs, _copilot, (), "cited answer or abstention (Copilot)"
        ),
        ToolSpec("get_flex_run", T0, OBS, rag_tools.GetFlexRunArgs, _rag("get_flex_run"), F, "one FLEX run"),
        ToolSpec(
            "flex_summary", T1, MOD, rag_tools.FlexSummaryArgs, _rag("flex_summary"), F, "descriptive stats"
        ),
        ToolSpec(
            "validate_comparison",
            T1,
            None,
            rag_tools.ComparisonRequest,
            _rag("validate_comparison"),
            (),
            "comparability gate",
        ),
        ToolSpec("list_methods", T0, None, rag_tools.NoArgs, _rag("list_methods"), (), "method cards"),
        ToolSpec(
            "fit_burning_rate_constant",
            T1,
            MOD,
            rag_tools.DropletSeries,
            _rag("fit_burning_rate_constant"),
            (),
            "d2-law fit of supplied data",
            arg_sources=_provenance_source,
        ),
        ToolSpec(
            "physics_oxygen_effect", T1, MOD, PhysicsArgs, _physics("oxygen_effect"), F, "O2-K association"
        ),
        ToolSpec(
            "physics_d2_consistency", T1, MOD, PhysicsArgs, _physics("d2_consistency"), F, "d2 consistency"
        ),
        ToolSpec(
            "simulation_request", T2, MOD, SimulationArgs, _simulation, (), "future simulation (approval)"
        ),
    )
}
