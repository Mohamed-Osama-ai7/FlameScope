# MVP Scope and Workflow

## Hackathon MVP: prove one complete scientific workflow

The strongest MVP is one end-to-end question answered from at least one official challenge Resources-tab NASA source, plus supporting public NASA material where appropriate. Do not attempt to ingest every PSI investigation in the hackathon window.

### Gate 0 — Challenge-resource eligibility

- Open the official Flame in Freefall challenge page → Resources tab.
- Record at least one NASA source from that exact list in `source_registry.csv`.
- Download it; record exact URL, retrieval time, release/version and license.
- Link every derived datum and demo claim to the resource/source artifact.
- If the Resources tab cannot be accessed, contact the Local Lead / Global Organizing Team. Do not assume another PSI investigation substitutes for the required challenge resource.

### Gate 1 — Data audit

Inventory the actual files. Determine formats, sizes, variables, units, test/run identifiers, metadata completeness, calibration, missingness, and license. Separate report-derived values from raw telemetry and image-derived measurements.

### Gate 2 — One regime-specific analysis

Choose the regime with the cleanest inspectable data and defensible labels. Candidate starting points are FLEX droplet combustion (PSI-69), BASS-II solid-material combustion (PSI-25), or SAFFIRE spacecraft-scale experiments (PSI-98), but final choice must follow the data audit and official challenge resource check.

### Gate 3 — Evidence retrieval and comparison

Start with source-grounded search and deterministic filters. Add hybrid retrieval only after a small evaluation set exists. Comparisons must state what is held constant and what differs. Reject invalid cross-regime comparisons rather than forcing a numeric ranking.

### Gate 4 — Scientific analysis

Implement one well-sourced calculation or model. Include units, assumptions, valid operating domain, uncertainty propagation, and independent checks. If required inputs are absent, return “not computable from available evidence.”

### Gate 5 — Interactive dashboard

Show the experiment context, evidence cards, comparison validity, analysis charts, uncertainty, and limitations. The dashboard must not hide the source or imply that a research heuristic is an operational safety limit.

### Gate 6 — Copilot (only after the evidence path works)

Use an LLM to interpret the retrieved evidence and call whitelisted Python/SQL tools. The LLM must not invent measurements or perform authoritative scientific calculations itself. If evidence is insufficient, abstain.

## Full product roadmap

1. Scientific Data Foundation: source ingestion, metadata, provenance, normalized schema, data-quality reports.
2. Scientific Intelligence & Physics: retrieval, comparisons, regime guardrails, physics/statistics, uncertainty, sensitivity.
3. AI Research Intelligence: grounded copilot, research-gap mapping, next-experiment design, calibrated computer vision.
4. Integration & Validation: reproducibility, independent tests, security, performance, documentation and submission package.
