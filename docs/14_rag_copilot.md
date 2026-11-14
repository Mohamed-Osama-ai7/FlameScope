# 14 — Scientific Intelligence Layer: evidence retrieval and grounded Copilot

Branch `feat/rag-scientific-copilot` (first built 2026-11-13; eligibility and Data Platform integration
2026-11-14; uncommitted). Code: `backend/app/rag/`, `backend/app/api/rag_routes.py`. Frontend contract:
[16_rag_frontend_handoff.md](16_rag_frontend_handoff.md). Nothing here changes an existing endpoint, the
v0.1.0/v0.2.0 analyses or the Scientific Exploration Lab.

## 1. Modules

| Stage | Module | Notes |
|---|---|---|
| Source eligibility | `eligibility.py` + `data/metadata/source_eligibility.csv` | Shared registry is the base; the decision file can only restrict (section 2) |
| Shared identifiers | `ids.py` | Data Platform contract formulas (namespace `urn:flamescope:data-platform:v1`); `chunk_id` = UUIDv5 of (artifact_id, chunker_version, chunk_index), the `document_chunks` unique key |
| Measurements | `measurements.py` | 2,466 PSI-69 cells with platform `measurement_id`, value status, `usable_for_analysis`, flags, locator; evidence status CLEAN / QUALIFIED / INVALID / MISSING |
| Ingestion | `ingest.py` | Artifact SHA-256 verified before parsing; PSI-69 rows rendered one statement per measurement; ineligible sources indexed only to be excluded |
| Chunking | `chunking.py` | Sentence windows ≤110 words, 1-sentence overlap; never crosses a page/section; rows and captions atomic |
| Retrieval | `bm25.py`, `dense.py`, `fusion.py`, `retriever.py`, `rerank.py` | BM25 default; optional BGE-M3 / hybrid RRF; ineligible chunks are never candidates on public routes |
| Query analysis | `query_analysis.py` | Fuels, regimes, experiment ids, measured variables, named sources, comparison intent |
| Tools | `tools.py` | `get_flex_run` returns measurement facts (value only when it may be stated); `flex_summary`, `validate_comparison`, `fit_burning_rate_constant`, `list_methods` |
| Citation validation | `citations.py` | Retrieved + eligible chunk, verbatim quote, traceable numbers, flagged/missing cells cannot be stated as values |
| Data Platform bridge | `platform.py` | Contract B.5 check of every cited measurement when the platform DB is configured; `sync_document_chunks` |
| Copilot | `copilot.py` | Comparison gate → source gate → sufficiency gates → tools → generation → validation → on-topic filter → platform verification |
| Evaluation | `evaluation.py`, `scripts/eval_rag.py`, `scripts/make_eval_v2.py`, `backend/eval/` | Retrieval + Copilot metrics, safety suite, exhaustive flagged-cell sweep |

## 2. Corpus and source eligibility (audited 2026-11-14)

Eligibility comes from `app/rag/eligibility.py`: the shared `data/metadata/source_registry.csv` (also read by
the Data Platform) is the base truth; `data/metadata/source_eligibility.csv` records the scientific owner's
decisions and can only restrict. Not registered → UNREGISTERED; registry QUARANTINED → QUARANTINED; no decision
recorded → not usable; VERIFIED_ELIGIBLE requires registry status VERIFIED. **These decisions are not changed
by code; changing them requires the scientific owner's approval.**

| Source | Chunks | Types | Eligibility | Usable |
|---|---|---|---|---|
| PSI-69 FLEX (CC0-1.0, sha256 `37c88ce8…1b96`) | 296 | 274 table rows + 22 record narrative | PENDING_VERIFICATION (primary candidate, final approval pending) | yes, status shown on every citation |
| PSI-25 BASS-II (CC0-1.0, sha256 `71e792bf…c48c042`) | 139 | 129 rows + 10 narrative | ACQUIRED_BUT_EXCLUDED | no |
| PSI-98 SAFFIRE-I | 13 | 4 rows + 9 narrative | QUARANTINED | no |
| NASA/TP-2015-216046 Appendix B captions | 276 | report captions (pypdf, not visually checked) | UNREGISTERED | no |

Total 724 chunks, 296 usable. PSI-69 measurements: 2,466 (the Data Platform's load count), of which 2,317
CLEAN, 37 QUALIFIED, 111 MISSING, 1 INVALID. The NASA/TP PDF hash (`b4f6ca98…e79d`, recorded in the derived
caption file) and the NTRS copyright statement ("Public Use Permitted", NTRS 20150023456) are kept on the
caption chunks for a future registration; until the report is registered and the captions are visually
checked they are never evidence. PSI-69 rows no longer contain caption-derived text, except one disclosed
caveat on FLEX-130's K ("caveat from the NASA/TP-2015-216046 enrichment, an unregistered source"). FLEX test
numbers themselves come from the approved v0.2.0 Table IX cross-match.

Every chunk carries: `chunk_id` (UUID), `chunk_key` (e.g. `PSI-69:row:070`), `artifact_id`, `artifact_path`,
`chunk_index`, `source_id`, title, URL, DOI, licence, `doc_type`, `regime`, `fuel_or_material`,
`experiment_ids`, `locator`, `locator_text`, `content_hash`, `source_artifact_sha256`, `verification_status`
(registry), `eligibility`, `exclusion_reason`, `usable_as_evidence`, `quality_flags`, `measurements[]`
(rows only), `ingestion_version` `ingest-1.1.0`, `chunker_version` `chunker-1.1.0`.

## 3. Measurement quality (B3/B4)

Values, flags and `usable_for_analysis` come from the verified FLEX loader that the Data Platform extractor
also uses; ids and locators follow the platform contract, and a combined test asserts that all 2,466 cells
equal the platform extraction (id, run, variable, unit, value, value status, usability, locator, flags).

| Evidence status | Rule | How it is stated |
|---|---|---|
| CLEAN | usable, no flag | `FLEX-070 initial droplet diameter: 4.67 mm (reported in the source).` |
| QUALIFIED | usable but flagged (approximate, zero meaning unconfirmed, Dext > D0, composition sum, FLEX-130 K caveat) | value + `QUALIFIED (<reason>)` |
| INVALID | value present, not usable (non-positive pressure, negative value) | `FLAGGED INVALID (<reason>); the source cell reads '0' mmHg, which is not usable as a measured value.` |
| MISSING | blank, dash marker, not a number | `MISSING in the source (<reason>); no value exists and none is substituted.` |

FLEX-129's extinction diameter (3.34 mm > D0 3.33 mm) is QUALIFIED, not INVALID: the platform keeps it
`usable_for_analysis = true` with a run-level flag. RAG never states it without the qualifier. **Decision
(Team Leader, 2026-11-14): keep QUALIFIED.** Changing it requires the scientific owner's approval.

Validation (`citations.py`): a claim may repeat a flagged value only with its marker; no number may be attached
to a MISSING or INVALID cell of a cited or named run; tool results expose `value` only for CLEAN/QUALIFIED.
Numbers for a named test and variable come from the backend measurement statement, never from model arithmetic.

## 4. Copilot behaviour

1. **Comparison gate**: cross-regime comparisons run `validate_comparison`; without `shared_axis_allowed` the
   answer is `comparison_blocked` with the reasons.
2. **Source gate**: a question naming only ineligible sources (BASS-II/PSI-25, SAFFIRE/PSI-98, NASA/TP)
   abstains with the source's eligibility and reason.
3. **Sufficiency gates**: named experiment present; named fuel present; no out-of-corpus terms; a value request
   without a named FLEX test abstains (per-run values are never pooled); retrieved evidence covers ≥60 % of the
   question's terms.
4. **Tools**, **generation**, **validation** (above), then an **on-topic filter**: a generated sentence must
   cover ≥50 % of the question's focus terms (set a priori, not tuned) or it is withheld; if nothing remains the
   Copilot abstains.
5. **Data Platform verification** (when configured): every cited measurement must exist, agree in status, value
   and unit, and belong to an ACQUIRED/VERIFIED investigation; otherwise the claim is dropped. If the database
   is configured but unreadable, numeric claims are withdrawn (`measurement_verification: unavailable`).

Statuses: `answered`, `answered_with_ambiguity`, `comparison_blocked`, `abstained`.

## 5. API (additive, prefix `/api/v1`) and configuration

Public: `GET /rag/status`, `GET /rag/sources`, `POST /rag/search`, `GET /rag/chunks/{chunk_id|chunk_key}`
(403 for ineligible chunks, no text), `GET /rag/tools`, `POST /copilot/ask`. Unknown request fields are
rejected (422), so `include_quarantined` no longer exists. Audit: `GET /rag/admin/excluded`,
`GET /rag/admin/chunks/{ref}`, `POST /rag/admin/search`, enabled only when `FLAMESCOPE_RAG_ADMIN_TOKEN` is set
(404 otherwise; 401 without the `X-FlameScope-Admin-Token` header; constant-time comparison).
Full response contract: [16_rag_frontend_handoff.md](16_rag_frontend_handoff.md).

Environment (`.env.example` lists all): `FLAMESCOPE_DENSE_BACKEND` (default `none`), `FLAMESCOPE_DENSE_MODEL`,
`FLAMESCOPE_RERANK_BACKEND`, `FLAMESCOPE_RERANK_MODEL`, `FLAMESCOPE_DEVICE`, `FLAMESCOPE_HYBRID_FUSION`,
`FLAMESCOPE_RRF_K`, `FLAMESCOPE_BM25_WEIGHT`, `FLAMESCOPE_DENSE_WEIGHT`, `FLAMESCOPE_RAG_CACHE`,
`FLAMESCOPE_LLM_PROVIDER`, `FLAMESCOPE_LLM_BASE_URL`, `FLAMESCOPE_LLM_MODEL`, `FLAMESCOPE_LLM_API_KEY`,
`FLAMESCOPE_LLM_TIMEOUT_S`, `FLAMESCOPE_RAG_ADMIN_TOKEN`, `FLAMESCOPE_DATABASE_URL` (Data Platform). No key is
hard-coded or echoed. Optional extra: `pip install -e ".[rag]"`.

**Default retrieval (decided 2026-11-13): BM25.** Hybrid BM25+BGE-M3 remains available per request.

## 6. Evaluation

### 6.1 v2 (2026-11-14, current corpus and eligibility)

Dataset `backend/eval/rag_questions_v2.jsonl`, derived mechanically from v1 by `scripts/make_eval_v2.py`
(every change recorded per question in `v2_change`): 9 questions whose gold was PSI-25 and 13 whose gold was a
NASA/TP caption became expected refusals; Q41 (composition and pressure of FLEX-100) stays answerable because
those facts are PSI-69 columns (relabelled after the first v2 run showed it — disclosed); 8 row quotes were
rewritten for chunker-1.1.0. Result: 48 questions, **19 answerable**, 29 unanswerable; dev 13 / test 6
answerable. Run: `scripts/eval_rag.py` (dense backend for the extra rows: `hashing`, an offline stand-in, not
neural). Output: `reports/rag_eval/results_v2_bm25_hashing.json`. Provider: extractive; **no LLM evaluated**.

**Not a held-out estimate.** The on-topic filter, the value-request gate, the "reported K" and "composition"
cues and the GENERIC modal words were added after inspecting failures on these same questions (both splits).
The numbers below are post-fix; an unseen question set is needed for an unbiased estimate. With 19 answerable
questions, one question moves a rate by about 5 points.

Retrieval (19 answerable, query only, no filters):

| Configuration | R@1 | R@5 | R@10 | MRR | nDCG@10 | median ms |
|---|---|---|---|---|---|---|
| bm25 | 0.868 | 1.000 | 1.000 | 0.947 | 0.961 | 0.74 |
| dense[hashing] | 0.737 | 0.947 | 0.974 | 0.828 | 0.863 | 0.63 |
| hybrid-rrf[hashing] | 0.868 | 1.000 | 1.000 | 0.947 | 0.961 | 1.29 |

BGE-M3 was **not re-run** on v2 (its v1 numbers below used the old corpus).

End-to-end Copilot, BM25 (all 48): false abstention 1/19 (Q32: "fiber-supported" exists only in the
unregistered captions, coverage 56 %); correct refusal 28/29; wrong answers on unanswerable 1 (Q40 "why was
no extinction diameter reported for FLEX-260": the Copilot states the cell is MISSING but cannot give the
reason, which is only in the unregistered caption); citation correctness (any gold cited) 1.0; strict citation
precision 0.722; answer contains gold quote 0.944; claims removed by validation 0; faithfulness lexical proxy
1.0 (trivially high for an extractive provider; not an entailment judge).

Safety (`backend/eval/rag_safety_v1.jsonl`, 16 cases): **16/16** — invalid (FLEX-114), qualified (FLEX-129,
FLEX-039), missing (FLEX-004, FLEX-009, FLEX-040), clean (FLEX-070), PSI-25 ×2, PSI-98, NASA/TP, invalid
comparisons ×2, unsupported ×3. Exhaustive sweep of every non-CLEAN PSI-69 cell (149: 111 MISSING, 37
QUALIFIED, 1 INVALID) asked as "What was the <variable> in <test>?": **149/149** reported with the right status
and marker and no exposed value. These were run without the Data Platform database
(`measurement_verification: loader_fallback`); the platform-verified path is covered by the integration tests
(section 9).

### 6.2 v1 (2026-11-13) — historical, superseded

Measured on the earlier corpus in which PSI-25 and the NASA/TP captions were (wrongly) usable evidence: 23 of
the 40 answerable v1 questions had gold in those sources, so these numbers describe a configuration that no
longer exists and are **not** evidence for the current system. Kept for the record in
`reports/rag_eval/results_hashing.json`, `results_bge-m3.json` and
`results_hashing_heldout_before_posthoc_fix.json`. Summary (40 answerable, BM25 / BGE-M3 dense / hybrid
RRF BGE-M3): R@5 0.925 / 0.875 / 0.963, MRR 0.833 / 0.712 / 0.868. The v1 test split was also not a clean
hold-out (post-hoc fixes after Q10, Q46). Reranking was never evaluated.

## 7. Scientific limitations

* Usable evidence is PSI-69 only (record narrative + table rows), and PSI-69 itself is pending final approval.
  Questions about BASS-II, SAFFIRE or report text abstain by design.
* Abstention for extrapolation is lexical (missing terms/entities, coverage, on-topic filter), not semantic.
* Contradictions are handled only by the comparison gate, eligibility, flags and same-identifier ambiguity.
* No LLM was run (no credentials); `openai_compat` is tested against a mock transport only.
* FLEX-129's extinction diameter is QUALIFIED by decision (section 3): stated only with its qualifier.

## 8. Commands

```bash
cd backend
.venv/Scripts/python -m pytest -q                                   # RAG + existing suite
.venv/Scripts/python -m ruff check app/rag app/api/rag_routes.py && .venv/Scripts/python -m mypy app
.venv/Scripts/python scripts/make_eval_v2.py                        # re-derive v2 from v1
FLAMESCOPE_DENSE_BACKEND=none .venv/Scripts/python scripts/eval_rag.py --label v2_bm25_hashing
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

## 9. Data Platform integration status (tested 2026-11-14)

Tested in a **temporary detached worktree** of `origin/feat/scientific-data-platform` (fb1a218) with this
branch's RAG files copied in and the routers added to that copy of `main.py`; no branch was modified, nothing
was merged. A real Alembic-migrated SQLite database was loaded by the platform loader.
`tests/test_rag_platform_integration.py` (skips when the platform package is absent) — 8/8 passed:

1. id formulas identical to `app.data_platform.ids`;
2. all 2,466 RAG measurements equal the platform extraction;
3. full workflow: registry → file SHA-256 → Copilot answer (FLEX-070, 4.67 mm) → platform
   `GET /measurements/{id}` and `/provenance` (same value, unit, artifact id and SHA-256, registry ACQUIRED) →
   chunk present in `document_chunks` with the same `chunk_id`;
4. FLEX-114 INVALID and FLEX-004 MISSING agree with the database;
5. withdrawn source (investigation set to QUARANTINED) → numeric claim dropped;
6. database unreadable → `unavailable`, no numeric claim;
7. `document_chunks` sync idempotent; 428 ineligible chunks never written;
8. `/rag/status` reports the platform connection.

Combined suite in that worktree: 255 passed, 4 skipped (PostgreSQL ×2, BGE opt-in, the RAG-only fallback
test), 3 failed — the three legacy CRLF hash-pin tests already listed by the platform team (their doc 14 §8.4);
not caused by RAG. PostgreSQL was not tested.

**Open integration items (owners):**

* `document_chunks` lacks eligibility, quality flags, content hash and measurement links; RAG therefore writes
  only eligible chunks and keeps full provenance in its own index (Data Platform owner: add columns or a
  side table).
* `ids.chunk_id` (namespace and key above) should be adopted in `app/data_platform/ids.py` (Data Platform
  owner).
* `source_eligibility.csv` is read only by RAG; the platform loader encodes the PSI-25 exclusion as "no
  extractor" (Data Platform owner + scientific owner: adopt the file or an equivalent registry column).
* PSI-25 narrative JSON artifacts and the NASA/TP PDF are not `source_artifacts` in the platform.
* Merge order: the platform branch and this branch both edit `backend/app/main.py`, `README.md` and
  `backend/pyproject.toml`; trivial conflicts expected (repository owner).
