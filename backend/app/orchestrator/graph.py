"""LangGraph workflow: REQUEST -> PLAN -> ELIGIBILITY -> APPROVAL -> EXECUTE -> VALIDATE -> CRITIC -> REPORT.

State holds plain JSON (pydantic dumps) so any LangGraph checkpointer can serialise it. The checkpointer is
injected: InMemorySaver is the default for tests and local development only and gives no durability. A
PostgreSQL checkpointer is a later integration (docs/23).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.orchestrator.audit import AuditEntry, AuditSink, InMemoryAuditLog
from app.orchestrator.contracts import (
    Claim,
    EligibilitySnapshot,
    EvidenceClass,
    PermissionTier,
    PlanStep,
    Provenance,
    ResearchPlan,
    ResearchReport,
    SourceUse,
    StepResult,
    canonical_sha256,
)
from app.orchestrator.planner import OfflinePlanner, Planner, validate_plan
from app.orchestrator.tools import REGISTRY, TOOLS_VERSION, source_use
from app.rag.query_analysis import analyse

INSTRUCTION_LIKE = re.compile(
    r"ignore (all |any )?(previous|prior) instructions|system prompt|you are now", re.I
)
PENDING_NOTE = "PSI-69 is PENDING_VERIFICATION: exploratory use only, not formal scientific evidence."


class ResearchState(TypedDict, total=False):
    run_id: str
    question: str
    plan: dict[str, Any]
    plan_notes: list[str]
    eligibility: dict[str, dict[str, Any]]
    snapshot: dict[str, Any]  # frozen EligibilitySnapshot dump, verified again at report time
    snapshot_hash: str
    blocked: dict[str, str]  # step_id -> reason (eligibility)
    approvals: dict[str, dict[str, Any]]
    steps: list[dict[str, Any]]
    gate: dict[str, str] | None  # {"status": ..., "reason": ...} ends the run early
    limitations: list[str]
    report: dict[str, Any]


class RunExistsError(ValueError):
    """A run id was reused: every start() must be a new run (approvals never carry over)."""


class RunNotFoundError(LookupError):
    pass


class RunNotAwaitingApprovalError(ValueError):
    pass


# Fields reset at the start of every run so nothing leaks from a previous state on the same thread.
_PER_RUN_RESET: dict[str, Any] = {
    "gate": None,
    "blocked": {},
    "approvals": {},
    "eligibility": {},
    "snapshot": {},
    "snapshot_hash": "",
    "steps": [],
    "limitations": [],
    "report": {},
    "plan_notes": [],
}


def _plan_steps(state: ResearchState) -> list[PlanStep]:
    return ResearchPlan.model_validate(state["plan"]).steps


def build_graph(
    planner: Planner | None = None, checkpointer: Any = None, audit_log: AuditSink | None = None
) -> Any:
    planner = planner or OfflinePlanner()
    sink = audit_log if audit_log is not None else InMemoryAuditLog()

    def audited(fn: Callable[[ResearchState], dict[str, Any]]) -> Any:  # LangGraph node
        """Nodes report events under "audit"; they go to the append-only log, never into graph state."""

        def node(state: ResearchState) -> dict[str, Any]:
            out = dict(fn(state))
            for event in out.pop("audit", []):
                sink.append(state["run_id"], event)
            return out

        return node

    def plan_node(state: ResearchState) -> dict[str, Any]:
        plan, notes = planner.propose(state["question"])
        errors = validate_plan(plan)
        if errors:  # never execute an invalid step: drop it, record why
            bad = {e.split(":")[0] for e in errors}
            plan = plan.model_copy(update={"steps": [s for s in plan.steps if s.step_id not in bad]})
            notes = notes + [f"rejected step {e}" for e in errors]
        out: dict[str, Any] = {
            **_PER_RUN_RESET,
            "plan": plan.model_dump(),
            "plan_notes": notes,
            "audit": [f"plan by {plan.planner}: {[s.tool for s in plan.steps]}"] + notes,
        }
        if not plan.steps:
            out["gate"] = {"status": "abstained", "reason": "no valid plan steps"}
        return out

    def eligibility_node(state: ResearchState) -> dict[str, Any]:
        qa = analyse(state["question"])
        steps = _plan_steps(state)
        if qa.cross_regime_comparison:
            return {
                "gate": {
                    "status": "comparison_blocked",
                    "reason": f"cross-regime comparison ({', '.join(qa.regimes)}): no shared axis",
                },
                "audit": ["comparison gate: blocked"],
            }
        needed = set(qa.sources) | {s for st in steps for s in REGISTRY[st.tool].sources_for(st.arguments)}
        uses = {s: source_use(s) for s in sorted(needed)}
        snap = EligibilitySnapshot(
            sources=uses, snapshot_hash=canonical_sha256({k: v.model_dump() for k, v in uses.items()})
        )
        out: dict[str, Any] = {
            "eligibility": {k: v.model_dump() for k, v in uses.items()},
            "snapshot": snap.model_dump(),
            "snapshot_hash": snap.snapshot_hash,
            "audit": [f"eligibility snapshot {snap.snapshot_hash[:12]}"],
        }
        # Conservative: a question that explicitly names an unusable source abstains, even when a usable
        # source is named too (e.g. "according to NASA/TP-2015-216046 ... FLEX-130"): the answer rests on it.
        bad_named = [s for s in qa.sources if not uses[s].exploratory_use]
        if bad_named:
            reasons = "; ".join(f"{s} is {uses[s].eligibility}" for s in bad_named)
            out["gate"] = {"status": "abstained", "reason": f"the named source is not usable: {reasons}"}
            return out
        out["blocked"] = {
            st.step_id: f"reads {s} ({uses[s].eligibility})"
            for st in steps
            for s in REGISTRY[st.tool].sources_for(st.arguments)
            if not uses[s].exploratory_use
        }
        return out

    def approval_node(state: ResearchState) -> dict[str, Any]:
        approvals = dict(state.get("approvals") or {})
        pending = [
            s
            for s in _plan_steps(state)
            if REGISTRY[s.tool].tier is PermissionTier.T2_APPROVAL and s.step_id not in approvals
        ]
        if not pending:
            return {}
        decision = interrupt(
            {
                "run_id": state["run_id"],
                "reason": "T2 operations need explicit approval",
                "pending": [s.model_dump() for s in pending],
            }
        )
        audit = []
        for s in pending:
            d = decision.get(s.step_id, {}) if isinstance(decision, dict) else {}
            ok = d.get("approved") is True and bool(str(d.get("approver", "")).strip())
            approvals[s.step_id] = {"approved": ok, "approver": str(d.get("approver", ""))}
            audit.append(
                f"approval {s.step_id} {s.tool}: {'APPROVED by ' + d['approver'] if ok else 'DENIED'}"
            )
        return {"approvals": approvals, "audit": audit}

    def execute_node(state: ResearchState) -> dict[str, Any]:
        results, audit = [], []
        blocked, approvals = state.get("blocked") or {}, state.get("approvals") or {}
        for s in _plan_steps(state):
            spec = REGISTRY[s.tool]
            base = {"step_id": s.step_id, "tool": s.tool, "tier": spec.tier}
            if s.step_id in blocked:
                results.append(
                    StepResult(**base, status="rejected", error=f"eligibility: {blocked[s.step_id]}")
                )
                continue
            if spec.tier is PermissionTier.T2_APPROVAL and not approvals.get(s.step_id, {}).get("approved"):
                results.append(StepResult(**base, status="not_executed", error="T2 operation not approved"))
                audit.append(f"{s.step_id} {s.tool}: not executed (no approval)")
                continue
            prov = Provenance(
                tool=s.tool,
                tool_version=TOOLS_VERSION,
                input_sha256=canonical_sha256(s.arguments),
                eligibility_snapshot_hash=state.get("snapshot_hash", ""),
            )
            try:
                outputs = spec.run(spec.args_model.model_validate(s.arguments))
            except Exception as exc:  # deterministic tool refused or failed: recorded, never retried silently
                results.append(
                    StepResult(**base, status="failed", error=f"{type(exc).__name__}: {exc}", provenance=prov)
                )
                audit.append(f"{s.step_id} {s.tool}: failed")
                continue
            prov.output_sha256 = canonical_sha256(outputs)
            unc = [PENDING_NOTE] if "PSI-69" in spec.reads_sources else []
            results.append(
                StepResult(
                    **base,
                    status="ok",
                    evidence_class=spec.evidence_class,
                    outputs=outputs,
                    provenance=prov,
                    uncertainty=unc,
                )
            )
            audit.append(f"{s.step_id} {s.tool}: ok {prov.output_sha256[:12]}")
        return {"steps": [r.model_dump(mode="json") for r in results], "audit": audit}

    def validate_node(state: ResearchState) -> dict[str, Any]:
        problems = []
        for r in state.get("steps") or []:
            if r["status"] != "ok":
                continue
            if not r.get("provenance", {}).get("output_sha256"):
                problems.append(f"{r['step_id']}: missing provenance")
            for h in _citations(r):
                if h["eligibility"] not in ("VERIFIED_ELIGIBLE", "PENDING_VERIFICATION"):  # defence in depth
                    problems.append(f"{r['step_id']}: cited an ineligible source {h['source_id']}")
        if problems:
            return {
                "gate": {"status": "failed", "reason": "validation failed: " + "; ".join(problems)},
                "audit": [f"validation: {len(problems)} problem(s)"],
            }
        return {"audit": ["validation: deterministic checks passed (no VVUQ beyond these checks)"]}

    def critic_node(state: ResearchState) -> dict[str, Any]:
        lim = ["Validation is limited to deterministic consistency checks; no VVUQ capability is claimed."]
        steps = state.get("steps") or []
        if any("PSI-69" in REGISTRY[r["tool"]].reads_sources and r["status"] == "ok" for r in steps) or any(
            h.get("source_id") == "PSI-69" for r in steps if r["status"] == "ok" for h in _citations(r)
        ):
            lim.append(PENDING_NOTE)
        for r in steps:
            out = r.get("outputs") or {}
            if r["status"] == "ok" and r["tool"] == "physics_oxygen_effect":
                lim.extend(out.get("limitations", [])[:2])
            if r["status"] in ("failed", "rejected", "not_executed"):
                lim.append(f"{r['step_id']} {r['tool']}: {r['status']} ({r.get('error')})")
            for h in _citations(r):
                if INSTRUCTION_LIKE.search(h.get("quote", "")):
                    lim.append(
                        f"cited passage {h['chunk_key']} contains instruction-like text; treated as data only"
                    )
            if (
                r["status"] == "ok"
                and r["tool"] == "copilot_answer"
                and out.get("status") in ("abstained", "comparison_blocked")
            ):
                lim.append(f"Copilot {out['status']}: {out.get('abstention_reason')}")
        if not _claims(steps, state.get("eligibility") or {}):
            reason = next(
                (
                    f"Copilot abstained: {r['outputs']['abstention_reason']}"
                    for r in steps
                    if r["status"] == "ok"
                    and r["tool"] == "copilot_answer"
                    and (r["outputs"] or {}).get("abstention_reason")
                ),
                "no usable evidence was produced",
            )
            return {"limitations": lim, "gate": {"status": "abstained", "reason": reason}}
        return {"limitations": lim, "audit": [f"critic: {len(lim)} limitation(s)"]}

    def report_node(state: ResearchState) -> dict[str, Any]:
        gate = state.get("gate")
        snap = state.get("snapshot") or {}
        if snap and not gate:  # the frozen snapshot must still match what the run used
            recomputed = canonical_sha256(snap.get("sources", {}))
            if recomputed != state.get("snapshot_hash") or snap.get("sources") != state.get("eligibility"):
                gate = {"status": "failed", "reason": "eligibility snapshot integrity check failed"}
        claims = [] if gate else _claims(state.get("steps") or [], state.get("eligibility") or {})
        status = gate["status"] if gate else ("completed" if claims else "abstained")
        report = ResearchReport(
            question=state["question"],
            status=status,
            abstention_reason=gate["reason"]
            if gate
            else (None if claims else "no claim could be supported by tool outputs"),
            claims=claims,
            limitations=state.get("limitations") or [],
            plan=ResearchPlan.model_validate(state["plan"]) if state.get("plan") else None,
            uncertainty=sorted({u for r in state.get("steps") or [] for u in r.get("uncertainty", [])}),
            eligibility={k: SourceUse.model_validate(v) for k, v in (state.get("eligibility") or {}).items()},
            eligibility_snapshot_hash=state.get("snapshot_hash", ""),
            steps=[StepResult.model_validate(r) for r in state.get("steps") or []],
        )
        return {
            "report": report.model_dump(mode="json"),
            "audit": [f"report: {status}, {len(claims)} claim(s)"],
        }

    def route_after(node: str) -> Any:
        def route(state: ResearchState) -> str:
            return "report" if state.get("gate") else node

        return route

    g = StateGraph(ResearchState)
    for name, fn in [
        ("plan", plan_node),
        ("eligibility", eligibility_node),
        ("approval", approval_node),
        ("execute", execute_node),
        ("validate", validate_node),
        ("critic", critic_node),
        ("report", report_node),
    ]:
        g.add_node(name, audited(fn))
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_after("eligibility"), ["eligibility", "report"])
    g.add_conditional_edges("eligibility", route_after("approval"), ["approval", "report"])
    g.add_edge("approval", "execute")
    g.add_edge("execute", "validate")
    g.add_conditional_edges("validate", route_after("critic"), ["critic", "report"])
    g.add_conditional_edges("critic", route_after("report"), ["report"])
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


def _citations(r: dict[str, Any]) -> list[dict[str, Any]]:
    if r.get("status") != "ok" or r.get("tool") != "copilot_answer":
        return []
    return [x for c in (r.get("outputs") or {}).get("claims", []) for x in c.get("citations", [])]


_STEP_SOURCES = {
    "get_flex_run": ["PSI-69"],
    "flex_summary": ["PSI-69"],
    "physics_oxygen_effect": ["PSI-69"],
    "physics_d2_consistency": ["PSI-69"],
}


def _tier(sources: list[str], eligibility: dict[str, dict[str, Any]]) -> str:
    formal = bool(sources) and all(eligibility.get(s, {}).get("formal_evidence") is True for s in sources)
    return "formal" if formal else "exploratory"


def _claims(steps: list[dict[str, Any]], eligibility: dict[str, dict[str, Any]]) -> list[Claim]:
    """Deterministic claim assembly from tool outputs only (no language model writes numbers)."""
    claims: list[Claim] = []
    for r in steps:
        if r["status"] != "ok":
            continue
        out, cls, sid = (
            r["outputs"] or {},
            EvidenceClass(r["evidence_class"]) if r.get("evidence_class") else None,
            r["step_id"],
        )
        if cls is None:
            continue
        if r["tool"] == "get_flex_run":
            for rec in out.get("records", []):
                for m in rec.get("measurements", []):
                    claims.append(
                        Claim(
                            text=m["statement"],
                            evidence_class=cls,
                            step_id=sid,
                            citations=[m["measurement_id"], f"PSI-69 row {rec['psi_row']}"],
                        )
                    )
        elif r["tool"] == "copilot_answer" and out.get("status") in ("answered", "answered_with_ambiguity"):
            for c in out.get("claims", []):  # already citation-validated by the Copilot
                claims.append(
                    Claim(
                        text=c["text"],
                        evidence_class=cls,
                        step_id=sid,
                        citations=[x["chunk_key"] for x in c["citations"]] + c.get("measurement_ids", []),
                    )
                )
        elif r["tool"] == "physics_oxygen_effect":
            for s in out.get("strata", []):
                if s.get("computable"):
                    b = s["model_k_on_o2"]["x_o2"]
                    claims.append(
                        Claim(
                            text=(
                                f"{s['fuel']}, {s['pressure_cluster']}: slope b1 = {b['estimate']:.2f} "
                                f"mm^2/s per unit X_O2 (95% CI {b['ci95'][0]:.2f} to "
                                f"{b['ci95'][1]:.2f}), n = {s['n']}; association, not causation"
                            ),
                            evidence_class=cls,
                            step_id=sid,
                            citations=[f"/api/v1/physics/oxygen-effect ({out['analysis_version']})"],
                        )
                    )
        elif r["tool"] == "physics_d2_consistency":
            for fuel, sm in out.get("by_fuel", {}).items():
                ci = sm.get("median_ci95") or [None, None]
                claims.append(
                    Claim(
                        text=f"{fuel}: median d2-consistency ratio r = {sm['median']:.3f} "
                        f"(95% CI {ci[0]:.3f} to {ci[1]:.3f}), n = {sm['n']}; diagnostic only"
                        if ci[0] is not None
                        else f"{fuel}: median r = {sm['median']:.3f}, n = {sm['n']}",
                        evidence_class=cls,
                        step_id=sid,
                        citations=[f"/api/v1/physics/d2-consistency ({out['analysis_version']})"],
                    )
                )
        elif r["tool"] == "flex_summary":
            claims.append(
                Claim(
                    text=f"Descriptive summary for {out.get('fuel')} from {out.get('provenance')}",
                    evidence_class=cls,
                    step_id=sid,
                    citations=[str(out.get("analysis_version"))],
                )
            )
    seen: set[str] = set()  # the same reported value may come from the run lookup and the Copilot
    unique = [c for c in claims if not (c.text in seen or seen.add(c.text))]  # type: ignore[func-returns-value]
    tools = {r["step_id"]: r["tool"] for r in steps}
    tiered: list[Claim] = []
    for c in unique:
        if tools.get(c.step_id) in _STEP_SOURCES:
            srcs = _STEP_SOURCES[tools[c.step_id]]
        else:  # Copilot claims: the sources of their validated citations ("PSI-69:row:070" -> PSI-69)
            srcs = sorted({k.split(":", 1)[0] for k in c.citations if ":" in k})
        tiered.append(c.model_copy(update={"sources": srcs, "evidence_tier": _tier(srcs, eligibility)}))
    return tiered


class ResearchOrchestrator:
    """Thin facade: start a run, resume after approval. One controlled workflow; no agent swarm."""

    def __init__(
        self, planner: Planner | None = None, checkpointer: Any = None, audit_log: AuditSink | None = None
    ) -> None:
        self.audit_log = audit_log if audit_log is not None else InMemoryAuditLog()
        self.graph = build_graph(planner, checkpointer, self.audit_log)

    def _state(self, run_id: str) -> Any:
        return self.graph.get_state({"configurable": {"thread_id": run_id}})

    def _report(self, result: dict[str, Any], run_id: str) -> tuple[ResearchReport, str]:
        if "__interrupt__" in result:
            pending = result["__interrupt__"][0].value["pending"]
            plan = ResearchPlan.model_validate(result["plan"])
            rep = ResearchReport(
                question=result["question"],
                status="awaiting_approval",
                plan=plan,
                abstention_reason="waiting for approval of: " + ", ".join(p["tool"] for p in pending),
                eligibility_snapshot_hash=result.get("snapshot_hash", ""),
            )
            return rep, run_id
        return ResearchReport.model_validate(result["report"]), run_id

    def start(self, question: str, run_id: str | None = None) -> tuple[ResearchReport, str]:
        """Start a NEW run. An existing run id is refused, so state and approvals never carry over."""
        run_id = run_id or str(uuid.uuid4())
        if self._state(run_id).values or self.audit_log.entries(run_id):
            raise RunExistsError(f"run '{run_id}' already exists; start a new run instead of reusing its id")
        cfg = {"configurable": {"thread_id": run_id}}
        result = self.graph.invoke({"run_id": run_id, "question": question}, cfg)
        return self._report(result, run_id)

    def resume(self, run_id: str, decisions: dict[str, dict[str, Any]]) -> tuple[ResearchReport, str]:
        """Resume a run that is paused for approval; decisions apply to that run's pending steps only."""
        state = self._state(run_id)
        if not state.values:
            raise RunNotFoundError(f"no run '{run_id}'")
        if not state.next:
            raise RunNotAwaitingApprovalError(f"run '{run_id}' is not waiting for approval")
        cfg = {"configurable": {"thread_id": run_id}}
        return self._report(self.graph.invoke(Command(resume=decisions), cfg), run_id)

    def audit(self, run_id: str) -> list[str]:
        return [e.event for e in self.audit_log.entries(run_id)]

    def audit_entries(self, run_id: str) -> tuple[AuditEntry, ...]:
        return self.audit_log.entries(run_id)
