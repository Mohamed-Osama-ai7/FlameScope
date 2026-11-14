# 21 — Data integrity and reproducibility release gates

Branch `feat/data-integrity-release-gates` from `feat/copilot-uncertainty-eval` (e0d49bb). Tests:
`backend/tests/test_integrity_gates.py`, strict raw-data mode in `backend/tests/conftest.py`. No eligibility or
scientific decision was changed; no raw NASA data is in Git.

## 1. Test portability (P0) — fixed

The 3 inherited failures (`test_v01_baseline_outputs_unchanged`, `test_provenance_matches_artifacts`,
`test_export_is_deterministic`) were CRLF hash pins: JSON artifacts had been hashed on Windows CRLF working copies
while Git stores LF. The verified fix from `feat/physics-analysis-engine` was ported: the artifact writers use
`newline="\n"` (`run_flex_analysis.py`, `build_flex_enrichment.py`, `export_lab_dataset.py` — one-line change, no
reformatting), the two v0.1 JSON pins are the committed bytes, and the lab dataset was regenerated. The regenerated
dataset is **byte-identical** to the physics branch's (SHA-256 `50e14bbf…db1ab3`) and differs from the previous file
only in `provenance.analysis_summary_sha256` and `provenance.captions_sha256`; no record, stratum or value changed.
The only file under `frontend/` touched is this generated data artifact (no UI code).

**Skips:** every data-dependent skip fires only when the gitignored raw file is absent (checked all 13 skip
sites). New strict mode: `FLAMESCOPE_REQUIRE_RAW_DATA=1` turns those skips into failures; verified by hiding the
data (2 skips → 2 failures) and restoring it.

## 2. Source integrity audit (P0)

| Source | Registry | Evidence decision | RAG | APIs | Lab export |
|---|---|---|---|---|---|
| CHALLENGE-RESOURCE-01 (PSI Combustion Science) | RESOURCE_RECORDED | not usable (catalogue) | not indexed | refused by analysis endpoint | not used |
| PSI-69 FLEX | ACQUIRED | PENDING_VERIFICATION, usable | usable, cited as PENDING_VERIFICATION | usable | source of all records |
| PSI-25 BASS-II | ACQUIRED | ACQUIRED_BUT_EXCLUDED | excluded (403, never retrieved) | **was accepted** (fixed) | not used |
| PSI-98 SAFFIRE-I | QUARANTINED | QUARANTINED | excluded | refused | not used |
| NASA/TP-2015-216046 | not registered | UNREGISTERED | excluded | computed only with "not traceable" warning | caption-derived fields labelled "not visually verified" |

No source is VERIFIED anywhere; nothing is described as approved (searched API responses, citations and the lab
export for "approved", "VERIFIED", "VERIFIED_ELIGIBLE").

**Violations found and fixed** (enforcing the existing decisions only):

1. `POST /api/v1/analysis/droplet/burning-rate-constant` checked only the registry, so `source_id: "PSI-25"` was
   accepted and the result presented as traceable to an excluded source. It now also applies the evidence decision
   (422 for PSI-25, PSI-98, CHALLENGE-RESOURCE-01; PSI-69 accepted; unregistered ids still computed with the
   existing "not traceable" warning).
2. The Copilot tool `fit_burning_rate_constant` had the same gap; same fix.
3. `GET /api/v1/status` listed PSI-25 in `sources_usable_as_evidence`; it now lists only PSI-69 and adds
   `evidence_eligibility` per source.

**Findings not changed (owner decisions):**

* PSI-25's exclusion lives in `data/metadata/source_eligibility.csv` (RAG) and in the Data Platform loader
  ("no extractor"); `GET /api/v1/sources` still shows only the registry status ACQUIRED. If an extractor were
  added, the loader would not consult the exclusion. Owner: Data Platform + scientific owner.
* The lab export keeps the invalid FLEX-114 pressure as `values.ambient_pressure = 0.0` with the flag in
  `field_flags`; consumers must honour flags (the frontend does). It also carries caption-derived support modes
  from the unregistered NASA/TP report (labelled "not visually verified") and does not state PSI-69's
  PENDING_VERIFICATION status. Owner: frontend/export owner.

## 3. Reproducibility (P1)

Verified by tests: registry SHA-256 = manifest SHA-256 = SHA-256 and size of each raw file (PSI-69, PSI-25,
PSI-98); lab-export provenance hashes = enrichment, captions, v0.2 summary and raw table; the NASA/TP PDF hash is
the same in the caption file, the export and the RAG locators. Deterministic exports: `test_export_is_deterministic`
passes; v0.2 outputs regenerate byte-identically on Windows (physics branch verification). Quality flags, missing
values and qualifiers are checked in three layers: Data Platform extraction (usable flag, value status, verbatim
text, locator, artifact hash), RAG chunks (INVALID / MISSING / QUALIFIED) and the lab export (field flags, nulls).

## 4. Challenge resource registration — unresolved

`CHALLENGE-RESOURCE-01` is recorded as "PSI Data Repository: Combustion Science" (RESOURCE_RECORDED, URL
`https://psi.nasa.gov/physci/repo/search?q=combustion`). The registry marks PSI-69, PSI-25 and PSI-98
`official_challenge_resource = YES` by **inference** from the PSI `researchArea` field. The Resources-tab listing
itself is not archived in the repository and could not be opened from this machine (TLS certificate error); the
Team Leader's confirmation is still pending. No mapping was guessed or changed.

## 5. Quality gate results

Full backend suite in strict raw-data mode with the real data: **290 passed, 0 failed, 4 skipped** (PostgreSQL ×2
without `FLAMESCOPE_TEST_DATABASE_URL`, optional BGE-M3 weights, and the no-platform fallback test that skips by
design when the platform package is present). Ruff and Mypy clean. PostgreSQL was not tested.
