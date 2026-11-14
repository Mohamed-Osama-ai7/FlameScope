# 22 — Integrity gap closure

Branch `feat/integrity-gap-closure` from `feat/data-integrity-release-gates` (f305bc2). No eligibility decision,
registry status or raw file was changed; the challenge-resource mapping stays pending.

## 1. Central PSI-25 exclusion

Evidence eligibility moved from `app/rag/eligibility.py` to the shared domain layer `app/domain/eligibility.py`
(RAG keeps a re-export). It is now enforced by:

* **Data Platform loader** — a source whose decision is not usable is refused *before* the extractor is looked up,
  and previously loaded measurements are withdrawn (`ACQUIRED_BUT_EXCLUDED in source_eligibility.csv; refused`).
  A test registers a fake PSI-25 extractor and shows it is never called.
* **Extractor** — refuses a source explicitly marked unusable in `source_eligibility.csv` (`explicit_exclusion`).
* **Analysis store** — rejects inputs from an investigation whose decision is not usable.
* Already enforced: RAG, `POST /analysis/droplet/...`, the Copilot fit tool, `GET /status` (doc 21).

`GET /api/v1/sources` still returns the registry (PSI-25 = ACQUIRED); the decision is exposed by `/status`,
`/rag/sources` and the investigation API below. The existing loader test now expects the exclusion reason instead of
"no extractor".

## 2. Support modes from the unregistered NASA/TP report

Support modes (free-floating / fiber) exist only in the NASA/TP-2015-216046 captions (unregistered). Changes:

* `run_analyses(..., stratify_by_support_mode=False)` and `run_flex_analysis.py --no-support-mode` produce
  **analysis v0.3.0** (`reports/flex_run_level_v0.3/`), where support mode is never an input; strata pool support
  modes and are labelled `support_mode = not_controlled`; charts no longer filter to free-floating droplets.
  The approved **v0.2.0 outputs are unchanged** and still regenerate byte-identically (default path).
* The Data Platform keeps the support mode as a derived run attribute with `support_mode_provenance` =
  unregistered, exploration label only. The lab export states the same in `evidence_status.support_mode`.
* Nothing was invented to replace support mode; it is reported as an uncontrolled confounder.

**Changed scientific outputs (v0.2.0 → v0.3.0):** 137 strata (38 with ρ) → 82 strata (34 with ρ). Pooling hides
support-mode differences, e.g. heptane O2 vs K at ~1 atm: free-floating ρ = 0.71 (n 23) and fiber-translated
ρ = −0.89 (n 5) in v0.2.0 become ρ = 0.49 (n 32) in v0.3.0; methanol at ~1 atm 0.89 (free) / 0.64 (fiber) → 0.82
(n 41). Per-stratum comparison: `reports/flex_run_level_v0.3/summary.json` vs `..._v0.2/summary.json`.

**Physics engine (branch `feat/physics-analysis-engine`, not modified here; re-run for this report):** its O2–K
model stratifies by support mode. Without it: computable strata 2 → 4; heptane ~1 atm slope 2.37 (95% CI
1.16–3.57, n 22, R² 0.52) → 1.97 (0.89–3.05, n 30, R² 0.36); methanol ~1 atm 1.91 (1.34–2.47, n 31) → 1.82
(1.43–2.21, n 39); new heptane ~0.7 atm 2.20 (n 9) and methanol ~0.7 atm 1.57 (n 12). The d^2 consistency check does
not use support mode (unchanged: medians 0.949 / 0.951). That branch should adopt the same rule.

**Remaining dependency on the unregistered report:** analysis A6 (extinction diameter) eligibility uses
`dext_origin`, which reads caption extrapolation notes; FLEX test numbers come from the approved Table IX
cross-match; the FLEX-130 K caveat in RAG comes from the same enrichment. Recorded in the v0.3.0 summary.

## 3. PENDING_VERIFICATION in every PSI-69 export

Lab export: new top-level `evidence_status` (eligibility read from the decision file, `approval_status: pending_verification`,
support-mode status, consumer rule); all pre-existing content is identical. Analysis v0.3.0 summary:
`evidence_eligibility`. Data Platform investigations (and therefore every provenance response):
`evidence_eligibility`. RAG citations already carried it.

## 4. Consumers reject flagged values

The export's per-field `usable` map (same rule as the analysis and the Data Platform) marks all 112 INVALID/MISSING
cells unusable. `app/analysis/export_guard.usable_value` returns a value only when it is usable and unflagged (FLEX-114
pressure `0.0` → None). Tests check every flagged cell, a stale-map case, and that no v0.2.0 or v0.3.0 stratum
contains a run whose x or y value is unusable. Frontend code was not changed (out of scope); it should use the
`usable` map or the same rule.

## 5. PostgreSQL

Not tested. Blocker: no PostgreSQL server or client is installed; the Docker CLI (29.9.1) is installed but its
engine is not running, and C: has ~690 MB free, too little for Docker Desktop's VM. The two PostgreSQL tests skip
without `FLAMESCOPE_TEST_DATABASE_URL`. To run them: start a PostgreSQL 16 instance (e.g. `docker compose up -d db`
from the repository root), then `FLAMESCOPE_TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/data_platform_tests/test_dp_postgres.py`.

## 6. Unchanged / pending

Challenge-resource mapping remains pending (inference from PSI `researchArea`; Resources tab not archived).
No eligibility decision was made.
