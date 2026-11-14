# UnderFitted — Sprint Ownership

| Workstream | Owner | Required output | Dependency |
|---|---|---|---|
| Technical direction & integration | Team lead | scope lock, architecture decisions, API contracts, integration and final QA | all workstreams |
| NASA data engineering | Data engineer | official resource manifest, immutable raw files, data inventory, extraction and provenance | challenge Resources tab |
| Combustion science & validation | Science lead | variable dictionary, regime definitions, one validated analysis, assumptions and limitations | actual data audit |
| Retrieval & AI | AI engineer | evidence search baseline, evaluation questions, grounded copilot/tool calls only when ready | clean source corpus |
| Frontend & story | Product/visualization engineer | evidence-led UI, charts, comparison flow, demo narration and report export | API/data contract |

## Integration cadence

- Every 3–4 hours: 10-minute interface check (what is done, what is blocked, what can be demoed).
- Every merge: tests, diff review, source/license review, no secrets or raw personal data.
- Keep one stable demo path at all times.
- A feature that threatens the demo path is cut or isolated behind a disabled/roadmap label.

## First-day sequence

1. Team lead confirms global registration/team page and official challenge resource eligibility requirement.
2. Data engineer acquires and inventories the challenge-supplied resource(s).
3. Science lead chooses the one analysis only after inspecting those files.
4. AI engineer builds a source-backed retrieval baseline; no unmeasured RAG KPI claims.
5. Frontend engineer builds the evidence-first workflow around the real data contract.
6. Team integrates a vertical slice before adding secondary modules.
