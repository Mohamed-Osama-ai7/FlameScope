# 16 — RAG / Copilot API: frontend handoff

Branch `feat/rag-scientific-copilot` (uncommitted, 2026-11-14). Base URL `http://127.0.0.1:8000/api/v1`.
Contract: request/response models in `backend/app/rag/schemas.py`, `copilot.py`, `citations.py`.
All examples below are real responses from this branch. Design and evaluation: [14_rag_copilot.md](14_rag_copilot.md).

## 1. Endpoints

| Method / path | Use in the UI | Errors |
|---|---|---|
| `POST /copilot/ask` | the Copilot panel | 422 invalid body (incl. unknown fields), 503 provider/backend cannot start |
| `POST /rag/search` | evidence search box | 422 (incl. unknown fields) |
| `GET /rag/chunks/{chunk_id or chunk_key}` | open a citation | 404 unknown, **403 ineligible source** |
| `GET /rag/sources` | source badges / legend | — |
| `GET /rag/status` | health / about page | 503 |
| `GET /rag/tools` | not needed by the UI | — |
| `GET /measurements/{id}/provenance` | "trace this number" (Data Platform route, contract docs/15) | 404/503; exists only when the Data Platform branch is merged |
| `/rag/admin/*` | **not for the UI** (audit only; disabled unless `FLAMESCOPE_RAG_ADMIN_TOKEN` is set; returns 404 when disabled, 401 without the `X-FlameScope-Admin-Token` header) | |

There is no way to request ineligible evidence from a public route: `filters.include_quarantined` and any
other unknown field are rejected with 422.

## 2. `POST /copilot/ask`

Request (only `question` is required):

```json
{"question": "What was the ambient pressure in FLEX test 114?", "top_k": 5, "mode": "bm25",
 "filters": {"source_ids": ["PSI-69"], "regimes": ["flex_droplet"], "doc_types": ["table_row"],
             "fuels": ["Heptane"], "experiment_ids": ["FLEX-070"]}}
```

`mode` defaults to `bm25`; `hybrid`/`dense` need a configured dense backend (otherwise a warning and BM25).

### Response fields the UI must handle

| Field | Meaning / how to render |
|---|---|
| `status` | `answered`, `answered_with_ambiguity` (show `warnings`; one identifier maps to several records), `comparison_blocked` (show `answer`, it explains why), `abstained` (show `abstention_reason`; no answer) |
| `answer` | concatenation of the claim texts; prefer rendering `claims` one by one |
| `claims[].text` | a verbatim evidence statement or backend measurement statement |
| `claims[].evidence_type` | `direct` or `analogous` (computed by the backend; style analogous differently) |
| `claims[].measurement_status` | `CLEAN`, `QUALIFIED`, `INVALID`, `MISSING` or `null` (narrative). **Never style INVALID/MISSING as a value.** QUALIFIED must be shown with its qualifier text (already in `text`) |
| `claims[].citations[]` | `chunk_id` (UUID), `chunk_key` (readable), `quote`, `source_id`, `source_title`, `source_url`, `doi`, `license`, `locator_text`, `artifact_id`, `source_artifact_sha256`, `eligibility`, `verification_status`, `quality_flags`, `measurements[]` |
| `citations[].eligibility` | show as a badge. Today every citable source is `PENDING_VERIFICATION` (PSI-69 awaits final scientific approval) — do **not** label it "verified" |
| `citations[].measurements[]` | `measurement_id`, `variable`, `unit`, `evidence_status`, `value` (null unless CLEAN/QUALIFIED), `quality_flags`, `source_locator`, `provenance` (relative URL of the Data Platform provenance route) |
| `evidence.missing` / `evidence.flagged` | lists to show under the answer ("not in the source", "flagged") |
| `measurement_verification` | `platform` (checked against the Data Platform DB), `loader_fallback` (ids follow the contract but no DB check — show a small "not DB-verified" note), `unavailable` (DB configured but down: numeric claims were withdrawn), `none` |
| `warnings` | show as notes |
| `source_eligibility` | `{source_id: eligibility}` for the cited (or, on abstention, named) sources |
| `notice` | fixed disclaimer; show it once in the panel |

Example (`answered`, an INVALID cell; trimmed):

```json
{"status": "answered",
 "claims": [{"text": "FLEX-114 ambient pressure: FLAGGED INVALID (an ambient pressure of zero or below is physically invalid); the source cell reads '0' mmHg, which is not usable as a measured value.",
   "evidence_type": "direct", "measurement_status": "INVALID",
   "measurement_ids": ["ce5330a1-3d97-5a8e-a092-4015f0cbdd69"],
   "citations": [{"chunk_id": "9ec327d1-a63d-57fb-a0de-aa2264049d16", "chunk_key": "PSI-69:row:114",
     "source_id": "PSI-69", "eligibility": "PENDING_VERIFICATION", "verification_status": "ACQUIRED",
     "artifact_id": "6848305b-ec73-5df8-aeea-e88b6b0cb7c3",
     "source_artifact_sha256": "37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96",
     "locator_text": "PSI-69 experimental table (FLEX), row 114",
     "measurements": [{"measurement_id": "ce5330a1-3d97-5a8e-a092-4015f0cbdd69", "variable": "ambient_pressure",
       "unit": "mmHg", "evidence_status": "INVALID", "value": null,
       "quality_flags": ["invalid_nonpositive_pressure"],
       "provenance": "/api/v1/measurements/ce5330a1-3d97-5a8e-a092-4015f0cbdd69/provenance"}]}]}],
 "evidence": {"direct": ["9ec327d1-..."], "analogous": [], "missing": [],
              "flagged": ["PSI-69-r114 ambient_pressure: INVALID (invalid_nonpositive_pressure)"]},
 "measurement_verification": "loader_fallback", "source_eligibility": {"PSI-69": "PENDING_VERIFICATION"}}
```

Example (`abstained`, excluded source):

```json
{"status": "abstained", "answer": "", "claims": [],
 "abstention_reason": "the source named in the question is not available as evidence; PSI-25 is ACQUIRED_BUT_EXCLUDED: Acquired and hash-verified but excluded pending scientific review: ...",
 "evidence": {"missing": ["usable evidence from PSI-25"]}}
```

## 3. `GET /rag/chunks/{ref}` for an ineligible source

```json
HTTP 403
{"detail": {"chunk_id": "ba41202b-9826-5ac5-b9a8-864afb2e3868", "source_id": "PSI-25",
            "eligibility": "ACQUIRED_BUT_EXCLUDED",
            "message": "not available as evidence; exclusion details are on the admin route"}}
```

No text is returned. Show "source not available as evidence" with the eligibility badge.

## 4. Source eligibility (from `GET /rag/sources`; decisions are the scientific owner's)

| source_id | eligibility | usable |
|---|---|---|
| PSI-69 (FLEX) | PENDING_VERIFICATION | yes (shown with this status) |
| PSI-25 (BASS-II) | ACQUIRED_BUT_EXCLUDED | no |
| PSI-98 (SAFFIRE-I) | QUARANTINED | no |
| NASA-TP-2015-216046 | UNREGISTERED | no |
| CHALLENGE-RESOURCE-01 | PENDING_VERIFICATION | no (catalogue entry) |

## 5. Stability

Field names above are stable for the handoff. Ids are deterministic (UUIDv5 in the Data Platform namespace):
a `chunk_id` or `measurement_id` does not change between restarts or reloads of the same source bytes and
chunker version (`chunker-1.1.0`). `chunk_key` is stable across chunker versions; prefer it in URLs shown to
users and `chunk_id` when calling the Data Platform.
