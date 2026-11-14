# 14 — Scientific Data Platform (Data Engineering / Backend / Scientific Data)

Workstream owner: Data engineer (sprint role 2 in [04_team_sprint.md](04_team_sprint.md)).
Branch: `feat/scientific-data-platform` (based on `release/v0.1.0-mvp`).
Status date: 2026-11-13.

This workstream turns acquired NASA files into a relational store that the rest of FlameScope can
rely on: every stored number resolves to the exact NASA bytes, row, and column it came from.

## 1. Deliverables

| Deliverable | Where | How it is verified |
|---|---|---|
| Verified NASA resource | `data/metadata/source_registry.csv` (`CHALLENGE-RESOURCE-01`, PSI-69, PSI-25, PSI-98) | `test_dp_contracts.py`; `/api/v1/status` → `official_challenge_resource_recorded: true` |
| SQLAlchemy models | `backend/app/data_platform/models.py` | Migration and models compared column by column (SQLite) and with `alembic check` (PostgreSQL) |
| Alembic migrations | `backend/alembic.ini`, `backend/app/data_platform/migrations/` | Upgrade → downgrade → upgrade on SQLite and PostgreSQL |
| PostgreSQL + Docker Compose | `docker-compose.yml`, `backend/Dockerfile` | `docker compose up` (section 7) |
| Reproducible data loader | `backend/app/data_platform/extract_flex.py`, `loader.py`, `backend/scripts/load_database.py` | Reload produces identical rows; tampered bytes are refused, and a refused load writes nothing |
| Data-quality validation | `extract_flex.run_quality_checks` → table `data_quality_checks` | `test_dp_extract.py`; `/api/v1/data-quality/PSI-69` |
| Provenance-aware API | `backend/app/data_platform/api.py`, `schemas.py` | `test_dp_api.py` |
| Backend tests | `backend/tests/data_platform_tests/` (73 tests: 71 run everywhere, 2 need PostgreSQL) | `pytest -q` (section 7) |
| Integration contract (API + RAG) | [15_integration_contract.md](15_integration_contract.md) | `test_dp_contract.py` keeps it in sync with the router |
| Generated SQL schema | `database/schema.sql` (offline rendering of the migrations) | `test_database_schema_sql_is_in_sync_with_migrations` |

## 2. A — NASA Resource Gate

**The official resource.** The challenge Resources tab (read 2026-11-13) lists, as its first item:

> PSI Data Repository: Combustion Science — "Physical Sciences Informatics (PSI) source of the data upon which the NASA Space App is to be based."
> URL: https://psi.nasa.gov/physci/repo/search?q=combustion

**Linking our files to it.** The PSI API (`https://psi.nasa.gov/geode-py/ws/repo/investigations/<id>`)
reports `researchArea = "Combustion Science"` for PSI-69 (FLEX), PSI-25 (BASS-II) and PSI-98 (SAFFIRE-I),
checked 2026-11-13. We therefore treat their experimental tables as data from that resource.

**Limits of this evidence.** The link between our files and the Resources tab is an inference from
the PSI `researchArea` field; the PSI search page itself was not captured. The Resources-tab text was
read through a web fetch on 2026-11-13 and is not archived in the repository. Before submission the
team lead should re-open the Resources tab in a browser and tick the item in
[06_nasa_compliance_checklist.md](06_nasa_compliance_checklist.md). Eligibility is decided by the
Global Organizing Team, not by this registry.

**Integrity.** The three tables were downloaded again on 2026-11-13 with
`backend/scripts/fetch_psi_table.py`. All three match the SHA-256 and byte sizes already recorded in
`artifact_manifest.csv`, and the manifest was unchanged, which shows the acquisition is reproducible.

| source_id | Status | Official | Usable as evidence | In the database |
|---|---|---|---|---|
| CHALLENGE-RESOURCE-01 | `RESOURCE_RECORDED` (new status: a catalogue, not a file) | YES | no (has no bytes of its own) | via PSI-69 |
| PSI-69 FLEX | `ACQUIRED` (sha256 `37c88ce8…1b96`, CC0-1.0) | YES | yes | **yes: 274 runs, 2,466 measurements** |
| PSI-25 BASS-II | `ACQUIRED` (sha256 `71e792bf…c48c042`, CC0-1.0) | YES | yes | no (section 8) |
| PSI-98 SAFFIRE-I | `QUARANTINED` (metadata conflict, doc 08) | YES | no | refused by design |

**Proof that the resource is actually used.** `GET /api/v1/data-platform/status` reports
`official_challenge_resource_loaded: true` only when rows from an official investigation whose registry
status is `ACQUIRED` or `VERIFIED` are stored.
Every measurement's provenance points to the PSI artifact (URL, SHA-256, licence, retrieval time).

New registry status `RESOURCE_RECORDED` (`app/domain/sources.py`): it requires `source_url` and
`retrieved_at_utc`, and it is never `usable_as_evidence`. A catalogue therefore cannot satisfy the
gate on its own; an acquired, hashed child file is still required.

## 3. B — Database architecture

```mermaid
flowchart LR
  REG[source_registry.csv<br/>artifact_manifest.csv] --> V{verify SHA-256 + size<br/>registry = manifest<br/>status usable}
  RAW[(data/raw — read-only)] --> V
  V -- mismatch / QUARANTINED --> X[refused, nothing written]
  V --> P[parse: app.analysis.flex_run_level<br/>same parser as the analysis]
  P --> Q{quality checks}
  Q -- structural ERROR --> X
  Q -- warnings become flags --> T[(PostgreSQL<br/>one transaction)]
  T --> API[FastAPI /api/v1] --> FE[Frontend] & RAG[RAG / Copilot]
```

```mermaid
erDiagram
  investigations ||--o{ source_artifacts : has
  investigations ||--o{ experimental_runs : has
  source_artifacts ||--o{ extraction_runs : "parsed by"
  source_artifacts ||--o{ experimental_runs : "row of"
  extraction_runs ||--o{ experimental_runs : produced
  extraction_runs ||--o{ measurements : produced
  extraction_runs ||--o{ data_quality_checks : recorded
  experimental_runs ||--o{ measurements : has
  source_artifacts ||--o{ measurements : "cell of"
  variables ||--o{ measurements : names
  units ||--o{ measurements : unit
  analysis_results ||--o{ analysis_result_inputs : uses
  measurements ||--o{ analysis_result_inputs : "input to"
  source_artifacts ||--o{ document_chunks : "chunked into"
```

Design decisions:

- **Deterministic IDs.** `measurement_id = uuid5(artifact sha256, row, raw header)`. `run_id = PSI-69-r001`, which is URL-safe and keyed on the PSI row (FLEX identifiers are not unique). A reload never changes a key, so links held by the frontend, RAG, or analysis results stay valid.
- **One source cell = one measurement row.** Outcomes never live on the run row. A run cannot carry a value without a unit, a locator, and an extraction method.
- **Missing is NULL, never 0.** The original marker is kept: `""` or an en dash. A database constraint enforces it: `value IS NULL` ⇔ `value_status ∈ {missing, unparseable}`.
- **Vocabulary from the science domain.** Variables and units come from `app/domain/regimes.py`. This workstream adds only `burn_time` (marked `defined_in = app.data_platform.vocabulary`). Unit and variable dimensions must agree, or the load is refused.
- **Derived values kept separate.** Diluent family, pressure cluster, support mode, and the FLEX report test number are stored in `experimental_runs.derived_attributes`, each naming what derived it. Source values are not mixed with them.
- **`analysis_results` inputs use a join table.** `analysis_result_inputs` replaces the old `BIGINT[]` with FK `ON DELETE RESTRICT`. A measurement used by an analysis cannot be removed silently.
- **Schema file is generated.** `database/schema.sql` is now generated from the migrations, so there is one source of truth.

## 4. C — Data quality & provenance

Every measurement carries these fields:

| Requirement | Column(s) |
|---|---|
| Source artifact | `artifact_id` → `source_artifacts` (file, URL, SHA-256, size, licence, version, retrieved_at, encoding) |
| Experiment / run | `run_id` → `experimental_runs` (PSI row, identifier, `source_record_key`, fuel, date, end mode); the investigation via `experimental_runs.investigation_id` |
| Variable | `variable_name` → `variables` (dimension, description) |
| Unit | `unit` → `units`, plus `original_unit_label` (as printed in the header) and `unit_evidence` (NASA citation) |
| Extraction method | `extraction_run_id` → `extraction_runs` (extractor name + version, input digests, code revision), plus `extraction_method` |
| Original location | `source_row`, `source_column` (raw header, verbatim), `source_locator` |
| Original value | `original_value_text` (verbatim), `value`, `value_status` |
| Quality flags | `quality_flags`, `usable_for_analysis` (the same rule as `FlexRun.usable` in the analysis) |

`source_locator` format (URL-encoded, because raw headers contain `;`):
`PSI-69_Experimental table_FLEX.csv#csv_line=2&flex_test=1&column=Burning%20rate%3B%20mm`.
Parse it with `app.data_platform.extract_flex.parse_locator`.

**Checks.** ERROR checks block the load. WARNING checks keep the data and flag it.

| Check | Severity | PSI-69 result |
|---|---|---|
| source_row_sequence, run_id_unique, measurement_cell_unique | error | pass |
| unit_in_vocabulary, variable_in_vocabulary, unit_dimension_matches_variable | error | pass |
| mole_fraction_within_0_1, original_text_preserved | error | pass |
| missing_values | warning | 111 cells (Dext 77, K 16, D0 12, burn time 6) |
| test_date_two_digit_year_assumed_20yy | warning | 50 runs |
| zero_value_meaning_unconfirmed | warning | 8 |
| composition_sum_deviation | warning | 6 runs |
| approximate (`~6`, `~9`) | warning | 2 |
| duplicate_source_identifier (193F001) | warning | 2 runs (r070, r073) |
| invalid_nonpositive_pressure | warning | 1 (r114) |
| dext_exceeds_d0, missing_test_time_gmt | warning | 1 each |
| usable_for_analysis | info | 2,354 usable / 112 not |

**Terminology and count reconciliation** (verified by SQL on the loaded PostgreSQL database):

| Number | Entity | Derivation |
|---|---|---|
| 1 | investigation | PSI-69 (FLEX) |
| 274 | test runs (`experimental_runs`) | one per data row of the PSI-69 table; 274 distinct FLEX report test numbers. Not "experiments": FLEX is one experiment. |
| 273 | distinct FLEX identifiers | `193F001` appears on rows 70 and 73 (same in NASA/TP Table IX) |
| 284 | tests stated by NASA/TP-2015-216046 | not all are in PSI; Table IX rows FLEX-216 and FLEX-230 are absent (doc 09) |
| 2,466 | measurements (source cells) | 274 runs × 9 numeric columns |
| 111 | cells with `value_status = missing` | blank or en dash; stored as NULL with the original marker |
| 1 | cell kept but invalid | r114 `ambient_pressure` = 0 mmHg (`invalid_nonpositive_pressure`) |
| 2,354 | `usable_for_analysis = true` | 2,466 − 111 − 1 |

These counts match `data/metadata/variable_dictionary.csv` and the analysis report.
Two tests check them independently. One re-reads the raw bytes and compares every stored cell, its
location and its verbatim text. The other compares every value with the frontend's
`flex_lab_dataset_v0.2.0.json`.

## 5. D — API contract (`/api/v1`, read-only)

| Method | Path | Purpose |
|---|---|---|
| GET | `/data-platform/status` | DB configured/reachable, schema revision vs expected, loaded investigations, counts. Never errors. |
| GET | `/status` (existing) | `scientific_dataset_loaded` is now derived from the database. New key `official_challenge_resource_loaded`. |
| GET | `/investigations`, `/investigations/{id}` | Investigation metadata, artifacts (SHA-256, licence), counts |
| GET | `/runs` | Filters: `investigation_id, combustion_regime, fuel, end_mode, has_flag`. `limit` up to 500, `offset`. |
| GET | `/runs/{run_id}` | Run + artifact + all 9 measurements |
| GET | `/measurements` | Filters: `investigation_id, run_id, variable, role, value_status, usable_only` (**default `true`**), `exclude_flag` (repeatable). `limit` up to 1000, `offset`. |
| GET | `/measurements/{id}` | One measurement |
| GET | `/measurements/{id}/provenance` | Source cell, run, investigation, artifact, extraction run, `how_to_verify` |
| GET | `/variables`, `/units` | Controlled vocabulary (with measurement counts) |
| GET | `/data-quality/{investigation_id}` | All checks of the latest load |

Conventions:

- Lists return `{items, total, limit, offset}` and are deterministically ordered.
- With no database configured, the API returns 503 with instructions. An unknown id returns 404. A bad filter returns 422; flags must match `^[a-z0-9_.:]{1,80}$`.
- Interactive docs are at `/docs`.

**Keeping invalid or quarantined data out of analysis and RAG:**

- `/measurements` returns only `usable_for_analysis = true` unless the caller passes `usable_only=false` (for inspecting missing or invalid cells). A missing cell is never returned as a number.
- QUARANTINED or not-acquired sources are refused by the loader, so their rows never enter the database (PSI-98).
- If a source that was already loaded is later set to a non-usable status in the registry, the next loader run withdraws it. Its measurements become `usable_for_analysis = false` with the flag `source_withdrawn`, and the investigation records the new status. Rows are kept for audit, and the status endpoint stops counting the source.
- `document_chunks.artifact_id` is a foreign key to `source_artifacts`, which holds only loaded, verified artifacts.
- `/runs/{run_id}` and `/provenance` still show every cell of a run with its flags: that is inspection, not analysis input.

Integration notes:

- **Frontend.** The current frontend calls only `GET /health` and reads the static `frontend/public/data/flex_lab_dataset_v0.2.0.json`, so no frontend change is required and no existing path changed. `runs.source_record_key` equals the dataset's `record_key`, and a test asserts that all values agree, so the UI can move to the API run by run. CORS allows `http://localhost:5173` (GET/POST), as before.
- **RAG / Copilot.** The branch `feat/rag-scientific-copilot` was not present on `origin` or locally on 2026-11-13, so its expected contract could not be checked. Proposed contract: cite `measurement_id` and resolve it through `/provenance`. Table `document_chunks` exists, keyed to `source_artifacts`, and is ready for the retrieval workstream. Tool calls should use `/measurements` filters instead of free text.
- **Science.** Persist results only through `app.data_platform.analysis_store.record_analysis_result`. It refuses empty, unknown, missing-value, unusable or withdrawn inputs before writing, and stores every input in `analysis_result_inputs` (doc 15 §B.6).

## 6. Configuration

| Variable | Meaning | Default |
|---|---|---|
| `FLAMESCOPE_DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://flamescope:flamescope_dev@127.0.0.1:5432/flamescope` | unset (API answers 503 on data routes) |
| `FLAMESCOPE_PROJECT_ROOT` | Repository root holding `data/` | auto-detected |
| `FLAMESCOPE_TEST_DATABASE_URL` | Enables the PostgreSQL integration tests (they create and drop a scratch database) | unset |
| `FLAMESCOPE_DB_USER/PASSWORD/NAME/PORT`, `FLAMESCOPE_API_PORT` | docker-compose overrides | `flamescope` / `flamescope_dev` / `flamescope` / 5432 / 8000 |

The default credentials are for local development only.

## 7. Runbook

```bash
# 0. raw NASA files (gitignored) - from the repository root
python backend/scripts/fetch_psi_table.py PSI-69 PSI-25 PSI-98 --root .

# 1a. Docker: PostgreSQL + API (the API applies migrations on start), then load
docker compose up -d --build
docker compose run --rm loader
# -> http://127.0.0.1:8000/docs , http://127.0.0.1:8000/api/v1/data-platform/status

# 1b. Without Docker for the API (PostgreSQL from compose)
docker compose up -d db
cd backend && pip install -e ".[dev,data]"
export FLAMESCOPE_DATABASE_URL=postgresql+psycopg://flamescope:flamescope_dev@127.0.0.1:5432/flamescope
alembic upgrade head
python scripts/load_database.py          # safe to re-run
uvicorn app.main:app --reload

# 2. Tests (SQLite layers always run; PostgreSQL layer when the URL is set)
FLAMESCOPE_TEST_DATABASE_URL=$FLAMESCOPE_DATABASE_URL pytest -q tests/data_platform_tests
ruff check app scripts tests && mypy app scripts

# 3. New migration after changing models.py
alembic revision --autogenerate -m "describe change"   # review it, then:
alembic upgrade head --sql > ../database/schema.sql    # and re-add the header
```

Loader exit codes: `0` loaded, `1` refused (nothing written), `2` configuration problem (no URL, or the schema is not at head).

## 8. Known limits & hand-offs

1. **PSI-25 (BASS-II) is not loaded.** The table needs science curation first: 51 free-text material descriptions, censored CO values (`>500`, `OR`, `over`), fan and air display readings that are not velocities, and an ambiguous `GMT`. It also has no flame-spread rate. The loader reports it as `SKIPPED` with this reason. Add `extract_bass2.py` once the science lead fixes the mapping in `variable_dictionary.csv`.
2. **Uncertainty columns are empty for PSI-69.** The source gives no per-value uncertainty. NASA/TP-2015-216046 §3.1.2 states ±50 µm for droplet size, but it does not define the uncertainty type (1σ or bound), so the value is not stored as a number.
3. **Line endings and hashes.** `core.autocrlf=true` on Windows rewrote line endings of hashed files, so a fresh Windows clone broke byte-level checks. The new `.gitattributes` marks `data/**`, `reports/**` and `frontend/public/data/**` as byte-exact.
4. **Three existing tests fail, unrelated to this branch.** Owner: science and frontend. With byte-exact files, these tests still fail. The pinned hashes were computed on CRLF copies of files whose git blobs are LF.
   - `test_flex_audit.py::test_v01_baseline_outputs_unchanged`: the pinned `summary.json` hash is `3969559d…`, the LF blob is `199136152f…`.
   - `test_lab_dataset.py::test_provenance_matches_artifacts`: the dataset embeds CRLF hashes for `flex_enrichment_v1_captions.json` and `flex_run_level_v0.2/summary.json`.
   - `test_lab_dataset.py::test_export_is_deterministic`: it regenerates the dataset in place, which exposes the same mismatch, and it also rewrites a tracked file during the test run.
   - Fix: regenerate on LF checkouts and update the pins in one commit by the artefact owner.
   - Baseline check (2026-11-14): fresh clones of `release/v0.1.0-mvp` (3ffef0a) with the raw PSI files copied in. With an LF checkout the same 3 tests fail. With a Windows CRLF checkout 4 fail; `test_v02_summary_records_provenance_and_scope` also fails there. This branch fails the same 3 as LF. They are pre-existing and not regressions, and `.gitattributes` removes the fourth failure on Windows.
5. **Frontend not containerised.** The Docker image holds the backend only.

## 9. Files touched outside `app/data_platform/`

| File | Change | Why |
|---|---|---|
| `app/domain/sources.py` | + status `RESOURCE_RECORDED` and its validation | Record the catalogue-type official resource |
| `data/metadata/source_registry.csv` | Filled CHALLENGE-RESOURCE-01; PSI-69/25/98 official = YES with evidence | Resource gate |
| `app/main.py` | Mounted the data-platform router | API |
| `app/api/routes.py` | `/status` derives `scientific_dataset_loaded` from the database | Removes a hard-coded flag |
| `tests/test_api.py` | Status test isolates the environment; expects `official_challenge_resource_recorded = true` | The gate is now recorded |
| `pyproject.toml` | + sqlalchemy, alembic, psycopg; ruff ignore for generated migrations | Dependencies |
| `database/schema.sql` | Regenerated from the migrations | Single source of truth |
| `.gitattributes` (new) | Byte-exact data files | Hash stability on Windows |
| `README.md` | Database quick start; resource-gate status and its limits | Entry point for the team |

## 10. Verification record (2026-11-13, Windows 11, Docker 29.6, PostgreSQL 16.4)

| Check | Command (from `backend/` unless noted) | Result |
|---|---|---|
| New tests, all layers | `FLAMESCOPE_TEST_DATABASE_URL=… pytest -q tests/data_platform_tests` | 73 passed |
| Full suite, no PostgreSQL | `pytest -q` | 185 passed, 2 skipped (PostgreSQL layer), 3 failed (pre-existing, section 8 item 4) |
| Full suite, with PostgreSQL | `FLAMESCOPE_TEST_DATABASE_URL=… pytest -q` | 187 passed, 3 failed (same 3) |
| Test count | 117 pre-existing + 73 new | 190 collected |
| Lint / types | `ruff check app scripts tests` · `mypy app scripts` | clean · no issues in 36 files |
| Migration drift | `alembic check` (in `test_dp_postgres.py`) | no differences |
| Clean start | repo root: `docker compose --profile tools down -v` → `docker compose up -d` | API up, schema `0001`, 0 rows |
| Load twice | repo root: `docker compose run --rm loader` ×2 | 274 runs, 2,466 measurements both times; 1 extraction run; 26 quality checks |
| Safe default | `GET /api/v1/measurements` · `?usable_only=false` | total 2,354 · 2,466 |
| Raw data immutability | `touch /srv/data/x` inside the API container | `Read-only file system` |

Run order matters for the 3 pre-existing failures: `test_export_is_deterministic` rewrites
`frontend/public/data/flex_lab_dataset_v0.2.0.json` in place. A second run on that rewritten file passes
2 of the 3. The figures above are from a clean working tree; restore the file with
`git checkout -- frontend/public/data` after running the suite.
