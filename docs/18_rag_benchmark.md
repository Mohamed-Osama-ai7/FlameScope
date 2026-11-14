# 18 — RAG + Copilot benchmark (golden set v3)

Branch `feat/rag-evaluation-benchmark` from `release/v0.1.0-mvp` (8180971). Code: `backend/app/rag/benchmark.py`,
`backend/scripts/benchmark_rag.py`, `backend/scripts/make_eval_v3.py`; data `backend/eval/rag_golden_v3.jsonl`;
results `reports/rag_eval/benchmark_v3_{baseline,after_dev_tuning}.json`; tests `backend/tests/test_rag_benchmark.py`.

## 1. Golden set v3 (blind)

36 items written from the approved corpus only (PSI-69 record narrative and table rows; usable chunks), **before
the retriever or Copilot was run on any of them**, and committed in `894df0c` before the baseline run. Table rows
were sampled with `random.seed(20261114)`; questions are paraphrased, not copied from chunk text. Every answerable
item has gold chunk keys and a gold quote that `verify_gold` checks as a verbatim span of a usable gold chunk.
No eligibility decision was changed and no excluded, quarantined or unregistered source is gold.

| Category | Items | Expected behaviour |
|---|---|---|
| direct (one measurement of one run) | 8 | answered, citing the run's row |
| comparison (two FLEX runs, same variable) | 4 | answered, citing both rows (no computed comparison) |
| scientific (PSI-69 record narrative) | 8 | answered, citing the narrative chunk |
| invalid_comparison (cross-regime) | 3 | comparison_blocked |
| unsupported (not in evidence, extrapolation, nonexistent test, pooling) | 7 | abstained |
| ineligible_source (PSI-25, PSI-98, NASA/TP) | 6 | abstained |

Split alternates within each category: dev 19 (10 answerable), test 17 (10 answerable).

## 2. Metrics

Retrieval (answerable items, query only): Precision@K, Recall@K (K = 1, 3, 5, 10), MRR, nDCG@10 (binary).
Precision@K is bounded by |gold|/K (most items have one gold chunk, so P@5 ≤ 0.2 for them); P@1 is the
informative precision. Copilot: status accuracy (overall and per category); abstention precision, recall, F1
(refusal = abstained or comparison_blocked); citation precision (gold citations / citations) and recall (gold
chunks cited); answer support (gold quote in the answer); comparison completeness (both rows cited); grounding
(every number in a claim occurs in its cited quotes or a tool result); verbatim citations (quote is a span of a
usable, retrieved chunk); ineligible citations. All deterministic (BM25, extractive provider; **no LLM**).

## 3. Results

| | Baseline dev | Baseline test | After dev tuning: dev | After dev tuning: test | After: all |
|---|---|---|---|---|---|
| P@1 | 0.90 | 1.00 | 0.90 | 1.00 | 0.95 |
| Recall@5 / @10 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| MRR | 0.950 | 1.000 | 0.950 | 1.000 | 0.975 |
| nDCG@10 | 0.963 | 1.000 | 0.963 | 1.000 | 0.982 |
| Status accuracy | 0.789 | 0.706 | 0.947 | **0.765** | 0.861 (baseline 0.750) |
| Abstention P / R / F1 | 0.73 / 0.89 / 0.80 | 0.58 / 1.00 / 0.74 | 1.00 / 0.89 / 0.94 | 0.64 / 1.00 / 0.78 | 0.79 / 0.94 / 0.86 |
| False / missed abstentions | 3 / 1 | 5 / 0 | 0 / 1 | 4 / 0 | 4 / 1 |
| Citation precision / recall | 0.76 / 1.00 | 0.77 / 1.00 | 0.83 / 1.00 | 0.81 / 1.00 | 0.82 / 1.00 |
| Answer support, grounding, verbatim | 1.0, 1.0, 1.0 | 1.0, 1.0, 1.0 | 1.0, 1.0, 1.0 | 1.0, 1.0, 1.0 | 1.0, 1.0, 1.0 |
| Ineligible citations | 0 | 0 | 0 | 0 | 0 |

Per category after tuning (all): ineligible_source 6/6, invalid_comparison 3/3, comparison 4/4, scientific 7/8,
direct 5/8, unsupported 6/7. With 10 answerable items per split, one item moves a rate by 10 points.

## 4. Weaknesses found and what was changed

Retrieval is not the bottleneck (gold in the top 5 for every answerable item). The weakness is **over-abstention on
paraphrased questions**: the out-of-vocabulary gate treats ordinary words as unsupported science terms, and
measured variables are recognised only under their canonical names.

Changes, each motivated **only by a dev failure** (`backend/app/rag/query_analysis.py`):

1. Comparison cue words (compare, differ, higher, ...) no longer count as content terms (G09). Cross-regime
   detection is unchanged; it uses the same cues separately.
2. "droplet at ignition", "started with the larger droplet", "how large was the droplet" map to the initial
   droplet diameter, which PSI-69 / NASA/TP App. A.1 define at igniter-on (G01, G11).

A stop-word addition ("among") was tried and **reverted**, because its motivating item (G16) is in the test split.
Rule 1 also fixed test item G12 ("differ"); that is a held-out improvement, not tuning on test.

Remaining failures (not tuned):

* test G02 "For how many seconds did the FLEX-124 droplet burn?" (burn time not recognised), G04 "chamber
  pressure" and G06 "tabulated" (out-of-vocabulary gate), G16 "among": over-abstentions. A general fix (skip the
  vocabulary gate when an experiment and a variable are resolved, and a standard stop-word list) is the next step;
  it should be measured on a new unseen set.
* dev G30 "average K of all methanol droplets": answered from a publications chunk via the descriptive-summary
  path. The label (abstain) is **disputed**: averaging is an explicit statistic, and an answer from the v0.2.0
  descriptive summary could be legitimate; the cited publications chunk does not support it. Left as labelled.

## 5. Limitations

36 items is small; dev was used for tuning, so only the test column is held out, and it has 17 items. Gold labels
were written by one developer from the corpus, not by an independent domain expert. No LLM was evaluated; grounding
and answer support are trivially high for an extractive provider. The corpus is PSI-69 only (other sources are
ineligible by decision), so the benchmark does not measure multi-source retrieval.

Reproduce: `cd backend && FLAMESCOPE_DENSE_BACKEND=none python scripts/benchmark_rag.py --label <name>`.
