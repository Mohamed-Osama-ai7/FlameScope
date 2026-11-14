# 20 — Uncertainty-aware Copilot answering (set v5)

Branch `feat/copilot-uncertainty-eval` from `feat/copilot-answer-eval` (7a1d154). Code `backend/app/rag/uncertainty.py`,
`backend/app/rag/uncertainty_eval.py`, `backend/scripts/eval_copilot_uncertainty.py`, `backend/scripts/make_eval_v5.py`;
data `backend/eval/copilot_uncertainty_v5.jsonl`; results `reports/copilot_eval/uncertainty_v5_*.json`;
tests `backend/tests/test_copilot_uncertainty.py`. Existing v1–v4 sets and results are unchanged.

## 1. What was added

Every Copilot response now carries `uncertainty[]`, built deterministically from the response's own evidence. Each
item has `kind`, `code`, `detail` and `evidence` (measurement, chunk or source ids from that response):

| Kind | Codes | Source of the statement |
|---|---|---|
| measurement | `no_reported_uncertainty`, `qualified_value`, `invalid_value` | PSI-69 gives no per-value uncertainty; loader quality flags |
| data | `missing_value`, `duplicate_identifier_records`, `source_pending_verification`, `not_verified_against_database`, `ineligible_source`, `absent_fuel`, `pooling_refused` | table cells, eligibility decisions, verification mode, gates |
| model | `reported_fit_value` (K is the FLEX team's D^2 fit), `derived_calculation`, `incompatible_regimes`, `extrapolation_refused`, `claims_failed_validation`, `provider_unavailable` | method semantics, comparison gate, new extrapolation gate |
| retrieval | `partial_evidence`, `sentences_withheld`, `unknown_experiment`, `out_of_corpus_terms`, `insufficient_coverage`, `no_evidence`, `no_relevant_sentence` | sufficiency gates and validation |

**No confidence score or probability is produced**, and no model self-reported confidence is used (a test asserts
the response has no such field). With a few dozen labels a probability could not be calibrated or validated.
Abstention is the only confidence decision; it is evaluated as selective prediction (coverage, selective accuracy,
risk on unanswerable items). Probability calibration is not reported because there is nothing valid to calibrate.

## 2. Set v5 (blind, unseen)

27 items, committed (`cbaf282`) before the annotation code or any v5 run existed. Table rows were sampled with
`random.seed(20261116)` from PSI-69 rows that are not gold in v3 or v4 (a test enforces no gold overlap), plus the
single INVALID cell (FLEX-114) and the duplicate identifier 193F001 phrased anew (both appeared in earlier
non-holdout suites). Categories: numeric 6, qualified/invalid 3, missing 4 (one asks "why", with forbidden causal
words), conflicting records 2, comparisons with flagged or missing values 4, out-of-domain 6, unsupported
conclusions 2. Facts are read verbatim from the corpus; required uncertainty codes follow from the source alone.
Split: diagnostic 14, holdout 13 (run once, after the fix).

## 3. Results

| | Diagnostic baseline | Diagnostic final | **Holdout (single run)** |
|---|---|---|---|
| Status accuracy | 0.929 | 1.000 | **1.000** |
| Abstention P / R | 1.00 / 0.75 | 1.00 / 1.00 | **1.00 / 1.00** |
| OOD abstention rate | 0.67 | 1.00 | **1.00** |
| Factual accuracy | 1.000 | 1.000 | **1.000** |
| Uncertainty-code recall | 1.000 | 1.000 | **1.000** |
| Unsupported explanations / contradictory codes / forbidden terms | 0 / 0 / 0 | 0 / 0 / 0 | **0 / 0 / 0** |
| Coverage / selective accuracy / risk on unanswerable | 1.0 / 1.0 / 0.25 | 1.0 / 1.0 / 0.0 | **1.0 / 1.0 / 0.0** |

Regression: the RAG safety suite (16 cases, 149-cell flagged sweep), the v3 benchmark floors and the v4
answer-level floors all still pass.

## 4. Failure found and fix

**U24 (diagnostic) "What would the burning-rate constant of methanol be at 5 atm?"** was answered with the K values
of two unrelated runs (FLEX-163 0.37, FLEX-088 0.53 mm^2/s): an extrapolation presented as data. The value gate
recognised only "what was/is the …". Fix: an extrapolation gate — a question asking for a predicted or hypothetical
value of a measured variable ("what would/will … be", predict, estimate, extrapolate) abstains with
`model:extrapolation_refused`. Chosen on the diagnostic split only; the holdout was run once afterwards.

## 5. Limitations

* Small: 13 holdout items. A perfect score bounds the error rate only loosely (one failure would be −8 points).
* The required codes and the annotator both follow the same source facts (flags, eligibility, K semantics), so
  code recall measures that the annotation is wired and complete, not an independent judgement of uncertainty.
* "Conflicting evidence" is limited to duplicate identifiers; semantic contradictions between passages are not
  detected. Measurement uncertainty is binary (none reported / flagged); PSI-69 gives no numeric uncertainties, and
  the ±50 µm in NASA/TP-2015-216046 §3.1.2 is not used (report unregistered, uncertainty type undefined).
* Extractive provider only; no LLM generator was evaluated.

Reproduce: `cd backend && FLAMESCOPE_DENSE_BACKEND=none python scripts/eval_copilot_uncertainty.py --split holdout --label <name>`.
