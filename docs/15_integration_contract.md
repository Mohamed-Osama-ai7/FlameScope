# 15 — Scientific Data Platform: Integration Contract

Audience: the Frontend and RAG / Copilot developers, and anyone writing analysis results.
Owner: Data engineering workstream (doc 14). Branch `feat/scientific-data-platform`. Contract version: `1.0`
(schema revision `0001`, extractor `psi69_flex_experimental_table` `1.0.0`). Status date: 2026-11-13.

The contract below is checked against the code by `backend/tests/data_platform_tests/test_dp_contract.py`.
That test fails if a route is added, removed or renamed without updating the endpoint table in Part A.
The examples are real responses from the Docker stack loaded with PSI-69.

---

## Part A — API contract

Base URL: `http://127.0.0.1:8000/api/v1` (Docker) · OpenAPI: `/openapi.json` · interactive docs: `/docs`.
All endpoints are `GET`, read-only, JSON, and need no authentication (local research prototype). CORS allows `http://localhost:5173`.

### A.1 Endpoints

| # | Method and path | Response | Errors |
|---|---|---|---|
| 1 | `GET /api/v1/data-platform/status` | `DataPlatformStatus` | never errors (reports problems in the body) |
| 2 | `GET /api/v1/investigations` | `InvestigationOut[]` | 503 |
| 3 | `GET /api/v1/investigations/{investigation_id}` | `InvestigationDetail` | 404, 503 |
| 4 | `GET /api/v1/runs` | `Page[RunSummary]` | 422, 503 |
| 5 | `GET /api/v1/runs/{run_id}` | `RunDetail` | 404, 503 |
| 6 | `GET /api/v1/measurements` | `Page[MeasurementOut]` | 404 (unknown variable), 422, 503 |
| 7 | `GET /api/v1/measurements/{measurement_id}` | `MeasurementOut` | 404, 422 (not a UUID), 503 |
| 8 | `GET /api/v1/measurements/{measurement_id}/provenance` | `ProvenanceOut` | 404, 422, 503 |
| 9 | `GET /api/v1/variables` | `VariableOut[]` | 503 |
| 10 | `GET /api/v1/units` | `UnitOut[]` | 503 |
| 11 | `GET /api/v1/data-quality/{investigation_id}` | `QualityReportOut` | 404, 503 |

The existing `GET /api/v1/status` also reports `scientific_dataset_loaded` and `official_challenge_resource_loaded` from the database.

### A.2 Query parameters

`GET /runs`. Results are ordered by `investigation_id`, then `source_row`.

| Param | Type | Default | Meaning |
|---|---|---|---|
| `investigation_id` | string | — | e.g. `PSI-69` |
| `combustion_regime` | string | — | `flex_droplet`, `bass_ii_solid`, `saffire_spacecraft_scale` |
| `fuel` | string | — | exact match, e.g. `Heptane`, `Methanol` |
| `end_mode` | string | — | exact match: `Extinction`, `Disruption`, `Completion` |
| `has_flag` | string `^[a-z0-9_.:]{1,80}$` | — | runs carrying this run-level flag |
| `limit` / `offset` | int 1–500 / ≥0 | 100 / 0 | paging |

`GET /measurements`. Results are ordered by `run_id`, then `variable_name`.

| Param | Type | Default | Meaning |
|---|---|---|---|
| `usable_only` | bool | **`true`** | only `usable_for_analysis = true`; pass `false` to inspect missing or invalid cells |
| `investigation_id`, `run_id` | string | — | scope |
| `variable` | string | — | must exist in `/variables`, otherwise 404 |
| `role` | `condition` \| `outcome` | — | |
| `value_status` | `parsed` \| `approximate` \| `missing` \| `unparseable` | — | combine with `usable_only=false` for missing cells |
| `exclude_flag` | string, repeatable | — | drop measurements carrying any of these flags |
| `limit` / `offset` | int 1–1000 / ≥0 | 200 / 0 | paging |

Path ids: `investigation_id` is a registry id (e.g. `PSI-69`), `run_id` is a string (e.g. `PSI-69-r001`), and `measurement_id` is a UUID.

### A.3 Response schemas

Every field is always present. Fields marked "nullable" may be `null`.

**`Page[T]`**: `items: T[]`, `total: int` (rows matching the filters, before paging), `limit: int`, `offset: int`.

**`MeasurementOut`**:

| Field | Type | Notes |
|---|---|---|
| `measurement_id` | UUID | stable (A.4) |
| `run_id` | string | → `RunSummary.run_id` |
| `variable_name` | string | → `/variables` |
| `role` | `condition` \| `outcome` | |
| `value` | number, nullable | `null` when the cell is missing or not a number; never `0` for a missing cell |
| `value_status` | `parsed` \| `approximate` \| `missing` \| `unparseable` | |
| `original_value_text` | string | the source cell, verbatim (`""` or `–` for missing) |
| `unit` | string | → `/units`, e.g. `mm^2/s`, `mmHg`, `mole_fraction` |
| `measured_or_derived` | `measured` \| `derived` \| `report_value` | PSI-69 values are `report_value` (reported by the FLEX team) |
| `usable_for_analysis` | bool | the gate for analysis and RAG |
| `quality_flags` | string[] | e.g. `approximate`, `missing_dash_marker`, `invalid_nonpositive_pressure`, `source_withdrawn` |
| `attributes` | object | e.g. `{"dext_origin": …}` on extinction diameter |
| `uncertainty_value`, `uncertainty_type`, `coverage_factor` | nullable | not provided by PSI-69 |
| `source_column` | string | raw header, verbatim |
| `source_locator` | string | `<file>#csv_line=N&flex_test=M&column=<URL-encoded header>` |

**`RunSummary`**: `run_id`, `investigation_id`, `source_row` (int), `source_identifier` (not unique upstream), `source_record_key` (nullable; equals the frontend dataset `record_key`), `combustion_regime`, `material_or_fuel` (nullable), `test_date` (ISO date, nullable), `test_date_raw`, `test_time_gmt_raw`, `end_mode` (nullable), `quality_flags` (string[]), `derived_attributes` (object computed by FlameScope, with `derived_by`), `source_locator`.
**`RunDetail`** = `RunSummary` + `artifact: ArtifactOut` + `measurements: MeasurementOut[]` (all 9 cells, usable or not).

**`InvestigationOut`**: `investigation_id`, `title`, `acronym`, `combustion_regime`, `source_repository`, `source_url`, `doi`, `license_id`, `research_area`, `official_challenge_resource` (bool), `registry_status` (`ACQUIRED`, `VERIFIED`, `QUARANTINED`, …).
**`InvestigationDetail`** = `InvestigationOut` + `run_count`, `measurement_count`, `artifacts: ArtifactOut[]`.

**`ArtifactOut`**: `artifact_id` (UUID), `investigation_id`, `artifact_kind`, `file_name`, `relative_path`, `media_type`, `text_encoding`, `byte_size`, `sha256`, `source_url`, `source_version`, `license_id`, `retrieved_at` (ISO datetime, UTC).

**`ExtractionRunOut`**: `extraction_run_id` (UUID), `extractor_name`, `extractor_version`, `inputs_json` (raw and enrichment paths with their SHA-256), `parameters_json`, `code_revision` (git SHA; `null` when loaded inside Docker, which has no git), `run_count`, `measurement_count`, `first_loaded_at`, `last_loaded_at`.

**`ProvenanceOut`**: `measurement: MeasurementOut`, `source_cell: SourceCell`, `run: RunSummary`, `investigation: InvestigationOut`, `artifact: ArtifactOut`, `extraction: ExtractionRunOut`, `extraction_method` (string), `how_to_verify` (string).
**`SourceCell`**: `file_name`, `source_row`, `source_column`, `original_value_text`, `original_unit_label` (unit as printed in the header, nullable), `platform_unit`, `unit_evidence` (citation that justifies the unit, nullable), `source_locator`.

**`VariableOut`**: `name`, `dimension`, `description`, `environmental`, `defined_in`, `measurement_count`. **`UnitOut`**: `symbol`, `dimension`.
**`QualityReportOut`**: `investigation_id`, `artifact_sha256`, `extraction: ExtractionRunOut`, `load_blocked` (always `false`: blocked loads write nothing), `counts` (e.g. `{"error_pass": 8, "warning_flagged": 9, …}`), `checks: QualityCheckOut[]` (`check_name`, `severity`, `outcome`, `affected_count`, `description`, `details_json`).
**`DataPlatformStatus`**: `database_configured`, `database_reachable`, `schema_revision`, `expected_schema_revision`, `investigations_loaded` (only investigations with status ACQUIRED or VERIFIED), `official_challenge_resource_loaded`, `runs`, `measurements`, `detail` (nullable).

### A.4 Stable IDs and relationships

```
investigation (PSI-69) 1─* run (PSI-69-r001 … r274) 1─* measurement (9 per run)
artifact (sha256)      1─* run, 1─* measurement            extraction_run 1─* run, measurement
```

| ID | Format | Stability |
|---|---|---|
| `investigation_id` | registry `source_id` | permanent |
| `run_id` | `{source_id}-r{source_row:03d}` | permanent for a source; the row number is unique, the FLEX identifier is not |
| `measurement_id` | UUIDv5(artifact SHA-256, source row, raw header) | identical across reloads of the same bytes. A new NASA file version (new SHA-256) yields new ids, and the old ids are removed by the next load. |
| `artifact_id` | UUIDv5(SHA-256, relative path) | identical across reloads |
| `extraction_run_id` | UUIDv5(extractor, version, input digests) | identical across reloads |
| `source_record_key` | frontend dataset `record_key` | join key to `frontend/public/data/flex_lab_dataset_v0.2.0.json` |

### A.5 Errors

| Status | When | Body |
|---|---|---|
| 404 | unknown investigation, run, measurement or variable; no load recorded | `{"detail": "run 'PSI-69-r999' not found"}` |
| 422 | invalid `has_flag` / `exclude_flag` value | `{"detail": "flag must match ^[a-z0-9_.:]{1,80}$"}` |
| 422 | FastAPI validation (bad UUID, `limit` out of range, bad `role` or `value_status`) | `{"detail": [{"type": "less_than_equal", "loc": ["query", "limit"], "msg": "...", ...}]}` |
| 503 | database not configured | `{"detail": "Scientific database not configured (FLAMESCOPE_DATABASE_URL is not set). ..."}` |
| 503 | database configured but unreachable | `{"detail": "Scientific database unreachable (OperationalError). Check `docker compose ps`."}` |

Clients should read `detail` as either a string or a list.

### A.6 Real examples

`GET /api/v1/measurements?variable=burning_rate_constant_mm2_s&limit=1`

```json
{"items": [{"measurement_id": "13b7b447-f281-5ab5-84b8-446c3a0d5971", "run_id": "PSI-69-r001",
  "variable_name": "burning_rate_constant_mm2_s", "role": "outcome", "value": 0.52, "value_status": "parsed",
  "original_value_text": "0.52", "unit": "mm^2/s", "measured_or_derived": "report_value",
  "usable_for_analysis": true, "quality_flags": [], "attributes": {}, "uncertainty_value": null,
  "uncertainty_type": null, "coverage_factor": null, "source_column": "Burning rate; mm",
  "source_locator": "PSI-69_Experimental table_FLEX.csv#csv_line=2&flex_test=1&column=Burning%20rate%3B%20mm"}],
 "total": 258, "limit": 1, "offset": 0}
```

`GET /api/v1/measurements/13b7b447-f281-5ab5-84b8-446c3a0d5971/provenance` (abridged: `measurement` and `run.derived_attributes` omitted)

```json
{"source_cell": {"file_name": "PSI-69_Experimental table_FLEX.csv", "source_row": 1,
   "source_column": "Burning rate; mm", "original_value_text": "0.52", "original_unit_label": "mm",
   "platform_unit": "mm^2/s", "unit_evidence": "NASA/TP-2015-216046, Dietrich et al. (2015), ... Table IX header unit mm2/s. PSI header lost the '2/s'.",
   "source_locator": "PSI-69_Experimental table_FLEX.csv#csv_line=2&flex_test=1&column=Burning%20rate%3B%20mm"},
 "run": {"run_id": "PSI-69-r001", "investigation_id": "PSI-69", "source_row": 1, "source_identifier": "20CAL08",
   "source_record_key": "PSI69-r001|FLEX-001|20CAL08|3/5/2009|17:22:03", "material_or_fuel": "Methanol",
   "end_mode": "Disruption", "test_date": "2009-03-05", "quality_flags": [], "...": "..."},
 "investigation": {"investigation_id": "PSI-69", "doi": "10.60555/mbq8-0451", "license_id": "CC0-1.0",
   "research_area": "Combustion Science", "official_challenge_resource": true, "registry_status": "ACQUIRED", "...": "..."},
 "artifact": {"artifact_id": "6848305b-ec73-5df8-aeea-e88b6b0cb7c3", "byte_size": 24776, "text_encoding": "cp1252",
   "sha256": "37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96",
   "source_url": "https://psi.nasa.gov/geode-py/ws/studies/PSI-69/download?file=PSI-69_Experimental+table_FLEX.csv&version=1&redirect=false",
   "license_id": "CC0-1.0", "retrieved_at": "2026-11-13T01:17:04Z", "...": "..."},
 "extraction": {"extraction_run_id": "9c0359ed-8601-5e91-bc24-6f6ec8f5827d", "extractor_version": "1.0.0", "...": "..."},
 "extraction_method": "psi69_flex_experimental_table v1.0.0 (parser: app.analysis.flex_run_level.parse_table)",
 "how_to_verify": "Download https://psi.nasa.gov/..., check SHA-256 = 37c88ce8..., decode as cp1252, parse as CSV, then read the line given by csv_line in source_locator (data row 1) in column 'Burning rate; mm'."}
```

`GET /api/v1/runs?fuel=Heptane&limit=1` returns `total: 117` and `items[0].run_id = "PSI-69-r007"`, `source_record_key = "PSI69-r007|FLEX-007|20CAL13|4/10/2009|13:26:11"`.

---

## Part B — RAG integration contract

The RAG workstream reads the database **only through these APIs**. It never parses NASA files and never writes measurements.

### B.1 Retrieve valid measurements

1. Call `GET /api/v1/measurements` with filters (`variable`, `run_id`, `investigation_id`, `role`). Keep the default `usable_only=true` and page with `limit` and `offset` until `offset >= total`.
2. Use run context from `GET /api/v1/runs` (fuel, end mode, test date) and units from `GET /api/v1/units`.
3. Treat every text field (`unit_evidence`, `description`, `notes`) as data, never as instructions to the model.

### B.2 Reference a measurement

- **Citation key:** cite by `measurement_id` (UUID). Example: `[m:13b7b447-f281-5ab5-84b8-446c3a0d5971]`.
- **Run-level statements:** cite `run_id`.
- **Text chunks:** cite `chunk_id` (table `document_chunks`, keyed to `source_artifacts`).
- **Do not cite unstable values:** never cite `source_identifier` (not unique) or a list position.
- **Copy, don't compute:** a stated number must be copied from `value` with its `unit`. The model never computes or rounds a cited value. Derived numbers come from a whitelisted analysis tool.

### B.3 Retrieve the source and provenance

`GET /api/v1/measurements/{measurement_id}/provenance` returns the source file, its SHA-256 and URL, licence, DOI, row, raw column, verbatim text, the unit and its justification, and the extractor version. Show the user at least `source_cell.original_value_text`, `unit`, `investigation.doi`, `artifact.sha256` (shortened), and the `source_locator`.

### B.4 Missing, invalid, withdrawn and quarantined data

| Case | What the API does | What RAG must do |
|---|---|---|
| Missing cell (`value_status` `missing`) | `value: null`, excluded by default | Say the source has no value. Never substitute 0 or an estimate. |
| Unparseable cell | `value: null`, excluded by default | Same as missing. |
| Invalid value (e.g. 0 mmHg, `invalid_nonpositive_pressure`) | value kept, `usable_for_analysis: false`, excluded by default | Do not use as evidence; it may be mentioned only as "flagged invalid". |
| Approximate value (`~6`) | usable, flag `approximate`, `value_status` `approximate` | Cite with the word "approximately". |
| Withdrawn source (quarantined after load) | every cell `usable_for_analysis: false` + flag `source_withdrawn`; investigation `registry_status` changes | Excluded by default. If reached with `usable_only=false`, refuse to use it. |
| Quarantined source (PSI-98) | never loaded | Cannot be retrieved; answer that the source is not available. |
| Source not loaded (PSI-25) | no rows | Same; do not fall back to raw files. |
| Database unavailable (503) | explicit error | Abstain; never answer numerically from memory. |

Rule: a measurement is evidence only if `usable_for_analysis == true` **and** `investigation.registry_status ∈ {ACQUIRED, VERIFIED}` in its provenance.

### B.5 Verify a citation against the original NASA source

Online check, no file access (required for every citation):

1. `GET /measurements/{id}` returns 200.
2. `usable_for_analysis` is `true`.
3. The cited number equals `value` and the cited unit equals `unit`.
4. `GET /measurements/{id}/provenance` shows `investigation.registry_status` ∈ {ACQUIRED, VERIFIED}.

Byte-level check (optional, for audits) follows `how_to_verify`:

1. Download `artifact.source_url`.
2. Confirm that SHA-256 equals `artifact.sha256` and the size equals `artifact.byte_size`.
3. Decode the bytes with `artifact.text_encoding` and parse them as CSV.
4. Read the line given by `csv_line`, using `parse_locator` from `app.data_platform.extract_flex` or URL-decoding.
5. Take the cell under the header `source_column` and check that it equals `original_value_text`.

A failed citation check means: drop the claim, or abstain.

### B.6 Writing analysis results (Science, and RAG tool outputs)

Persist results only through `app.data_platform.analysis_store.record_analysis_result(...)`. It refuses (before writing) when:

- there are no inputs;
- an input id is unknown;
- an input has no value;
- an input is not `usable_for_analysis`;
- an input's source is not ACQUIRED or VERIFIED;
- a non-computable result has no `abstention_reason`.

Every stored result keeps its exact inputs in `analysis_result_inputs`. A referenced measurement cannot be deleted, because the foreign key uses `ON DELETE RESTRICT`.

---

## Part C — Integration test scenarios

Scenarios 1–5 are executable: `pytest -q tests/data_platform_tests/test_dp_contract.py` (from `backend/`, needs the raw PSI-69 file).

| # | Scenario | Steps | Expected | Test |
|---|---|---|---|---|
| 1 | Retrieve a valid measurement | `GET /measurements?variable=burning_rate_constant_mm2_s&limit=1` | 200; `total` 258; `usable_for_analysis` true; numeric `value` | `test_s1_retrieve_valid_measurement` |
| 2 | Retrieve its provenance | `GET /measurements/{id}/provenance` | 200; artifact, run and investigation are consistent with the measurement | `test_s2_provenance` |
| 3 | Verify artifact and original value | hash the raw file; read the cell at `source_locator` | SHA-256 and size match; cell text equals `original_value_text`; `float(text) == value` | `test_s3_verify_against_source_bytes` |
| 4 | Reject invalid measurements | r114 pressure (0 mmHg) and a missing cell through `record_analysis_result` | `AnalysisInputRejected`; nothing written | `test_s4_invalid_inputs_rejected` |
| 5 | Reject quarantined or withdrawn sources | withdraw PSI-69 via the registry, then query and record | default query `total` 0; recording refused; PSI-98 never loaded | `test_s5_withdrawn_and_quarantined_rejected` |
| 6 | RAG citation workflow | RAG answers a question; each `[m:<uuid>]` passes the B.5 online check | every citation resolves, is usable, and value and unit match | **pending**: branch `feat/rag-scientific-copilot` is not available (checked 2026-11-13) |

Scenario 6 acceptance checklist for the RAG branch:

1. Every numeric claim carries a `measurement_id`.
2. All cited ids pass B.5 steps 1–4.
3. A question about r114 pressure is answered as "flagged invalid" or abstained.
4. A question about PSI-98 or PSI-25 returns "not available".
5. With the API stopped (503), the assistant abstains.
6. No cited value is 0 where the source cell is missing.

---

## Part D — Known integration blockers

1. **RAG branch unavailable.** `feat/rag-scientific-copilot` exists neither on `origin` nor locally, so scenario 6 and the RAG side of this contract are unverified.
2. **Existing analysis endpoint.** `POST /api/v1/analysis/droplet/burning-rate-constant` takes a D(t) series in the request body, not measurement ids. It refuses quarantined or not-acquired registry sources, but computes unregistered `source_id`s with a "not traceable" warning. PSI-69 has no D(t) series, so this endpoint is not fed from the database. Wiring it to `record_analysis_result` needs the science owner.
3. **Frontend.** No change required: it calls only `/health` and the static dataset. Moving to the API is optional and can be done run by run through `source_record_key`.
4. **Legacy test failures.** 3 tests fail outside this workstream (doc 14 §8). Not addressed here.
