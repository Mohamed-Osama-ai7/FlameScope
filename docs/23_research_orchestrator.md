# 23 — QUASAR Research Orchestrator (LangGraph)

Branch `feat/quasar-langgraph-orchestrator` from `origin/main` (bcd979e). Code: `backend/app/orchestrator/`
(`contracts.py`, `tools.py`, `planner.py`, `graph.py`); tests: `backend/tests/test_orchestrator.py`.
Optional dependencies: `pip install -e "backend[orchestrator]"` (`langgraph>=1.2,<2`, `langchain-core>=1.8,<2`).

## Workflow

`REQUEST → PLAN → ELIGIBILITY → APPROVAL → EXECUTE → VALIDATE → CRITIC → REPORT` as one LangGraph `StateGraph`
(no agents, no tool-calling loop). Any gate (no valid plan, unusable named source, cross-regime comparison,
validation failure, no supportable claim) routes straight to REPORT with an explicit status.

* **PLAN**: `OfflinePlanner` (deterministic rules on the existing query analysis) is the default.
  `LangChainPlanner` wraps an *injected* LangChain chat model (`with_structured_output`, or a
  `PydanticOutputParser` chain when the model has no native structured output). The model returns a typed
  `ResearchPlan` only. Every plan, from either planner, is validated: allowlisted tool, declared arguments only
  (undeclared keys are rejected), typed values, unique ids, at most 8 steps. An invalid LLM plan is rejected and the
  offline plan is used; the rejection is audited.
* **ELIGIBILITY**: the central policy (`app/domain/eligibility.py`) is copied into an immutable eligibility
  snapshot (content hash) for the run. Formal evidence (`VERIFIED_ELIGIBLE` only) is kept separate from
  exploratory use. A question that names an unusable source abstains, even if a usable source is named too
  (conservative). Steps whose tool reads an unusable source are rejected before execution.
* **APPROVAL**: T2 steps raise a LangGraph `interrupt`; the run pauses until `resume` with
  `{step_id: {"approved": true, "approver": "<name>"}}`. Missing approver or anything other than `approved: true`
  counts as denied; denied steps are never executed.
* **EXECUTE**: allowlisted adapters only (`tools.py`): `eligibility_lookup`, `copilot_answer` (the existing
  Copilot, unchanged, with all its gates), `get_flex_run`, `flex_summary`, `validate_comparison`, `list_methods`,
  `fit_burning_rate_constant` (reused from `app/rag/tools.py`), `physics_oxygen_effect`, `physics_d2_consistency`
  (existing deterministic physics), `simulation_request` (T2 placeholder: no simulation service exists, so even an
  approved request is recorded and not executed). Each result carries provenance (input/output SHA-256, tool
  version, eligibility-snapshot hash) and an evidence class.
* **VALIDATE**: deterministic consistency checks only (provenance present, no ineligible citation). No VVUQ
  capability is claimed.
* **CRITIC**: deterministic limitations (PSI-69 pending verification, physics limitations, failed or rejected
  steps, instruction-like text inside cited evidence, Copilot abstentions).
* **REPORT**: claims are assembled from tool outputs by templates; no language model writes numbers.

## Evidence class vs eligibility

`EvidenceClass` (OBSERVED / MODELLED / ILLUSTRATIVE) says how a result was produced; `SourceUse` says whether a
source may be used. PSI-69 values are OBSERVED *and* `exploratory_use=true, formal_evidence=false`
(PENDING_VERIFICATION). PSI-25 (ACQUIRED_BUT_EXCLUDED), PSI-98 (QUARANTINED) and NASA/TP-2015-216046
(UNREGISTERED) abstain.

## Persistence

The checkpointer is injected. The default `InMemorySaver` is for tests and local development only: paused runs
are lost on restart and nothing is durable. Production needs a durable LangGraph checkpointer (e.g. the PostgreSQL
saver package) wired to the agreed database, plus storage of `ResearchRun` / `EligibilitySnapshot` records once
their schema is decided; neither is part of this change. No API route is added yet; the orchestrator is a library
(`ResearchOrchestrator.start / resume / audit`).

## Run binding, audit and snapshot guarantees (after the production-readiness audit)

* **One run per id.** `start()` refuses a run id that already exists (`RunExistsError`), and the plan node resets
  every per-run field, so approvals, gates or eligibility can never carry over from another run. `resume()` raises
  `RunNotFoundError` for an unknown run and `RunNotAwaitingApprovalError` for a run that is not paused, so a decision
  can never re-run a finished run.
* **Audit log.** Events go to an injectable append-only, hash-chained log (`audit.py`), one chain per run; entries
  are frozen and `verify()` detects edited or dropped entries. The default `InMemoryAuditLog` is process memory
  only, not a durable store.
* **Eligibility snapshot.** The frozen snapshot is stored with the run and re-hashed at report time; a mismatch
  fails the run. Reports carry `eligibility_snapshot_persistent: false` until a durable store is integrated.
* **Evidence tier per claim.** Each claim lists its sources and an `evidence_tier`: `formal` only when every
  source is `VERIFIED_ELIGIBLE`, otherwise `exploratory` (all PSI-69 claims today).
* **Sources inside arguments** (e.g. a fit's `provenance.source_id`) are gated like the sources a tool reads.
