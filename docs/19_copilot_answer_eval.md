# 19 — Copilot answer-level evaluation (set v4)

Branch `feat/copilot-answer-eval` from `feat/rag-evaluation-benchmark` (09852cf). Code `backend/app/rag/answer_eval.py`,
`backend/scripts/eval_copilot_answers.py`, `backend/scripts/make_eval_v4.py`; data `backend/eval/copilot_answers_v4.jsonl`;
results and reviews `reports/copilot_eval/`; tests `backend/tests/test_copilot_answer_eval.py`.

## 1. Set v4 (blind, separate)

34 items written from approved PSI-69 evidence before any run and committed first (`03863e9`). Table rows were
sampled with `random.seed(20261115)` from rows **not** used in v3 (a test checks the disjointness); narrative gold
uses chunks not used as v3 gold. Categories: numeric paraphrases 10, flagged/missing values 4, two-run comparisons 4,
scientific narrative 6, unanswerable 10 (out-of-evidence, nonexistent test, extrapolation, PSI-25, PSI-98, NASA/TP,
cross-regime ×2, absent fuel). Split: `diagnostic` 17 (used to choose fixes) and `holdout` 17 (**run once, after
the fixes**). Numeric items carry the exact source statement a correct answer must contain (`facts`); every gold
quote and fact is verified verbatim in an eligible gold chunk.

## 2. Checks

Deterministic per answer: status (answered / abstained / comparison_blocked); factual correctness (all gold
facts verbatim in the answer; a refusal counts as incorrect); claim support (citation present, quote verbatim in a
usable retrieved chunk, every number in the claim in its quotes or a tool result); off-target claims (cite no gold
chunk); ineligible citations. Independent review of narrative claims and of answered unanswerable items: a fresh
reviewer agent with no access to the code or results judged each claim against its cited text
(`reports/copilot_eval/review/*_review.json`). This is an LLM reviewer, **not** a human domain expert.

## 3. Results

| | Diagnostic baseline | Diagnostic final | **Holdout final (single run)** |
|---|---|---|---|
| Status accuracy | 0.824 | 1.000 | **0.824** |
| Factual accuracy (fact items) | 0.667 | 1.000 | **1.000** |
| Abstention precision / recall | 0.63 / 1.00 | 1.00 / 1.00 | **0.67 / 0.80** |
| False / missed abstentions | 3 / 0 | 0 / 0 | **2 / 1** |
| Claims / supported / unsupported | 15 / 1.0 / 0 | 18 / 1.0 / 0 | **17 / 1.0 / 0** |
| Off-target claims (answered items) | 4 | 4 | 2 |
| Ineligible citations | 0 | 0 | **0** |
| Independent review (narrative) | 2 correct, 1 partial | — | A20 correct; A34 **incorrect** |

After the A34 fix (`answers_v4_*_post_holdout_fix.json`): diagnostic unchanged (1.000); holdout status accuracy
0.882, factual 1.0, claim support 1.0, missed abstentions 0, false abstentions 2 (A22, A24). The held-out figure
remains the single run above (0.824).

v3 benchmark regression check (not tuned): test status accuracy 0.765 → 0.824 (the "chamber pressure" item is now
resolved by the measurement rule); retrieval unchanged; safety suite, the 149-cell flagged sweep and all RAG tests pass.

## 4. Failures and fixes (with reproducible examples)

Fixed (chosen on diagnostic only):

1. **Numeric paraphrases abstained** — A01 "How long did the flame last in FLEX-161?", A09 "How many seconds did
   FLEX-099 burn?", A03 "How big was the droplet when its flame went out in FLEX-086?". Added burn-time and
   extinction-diameter cues, and when the named run's requested measurement is in the retrieved row the coverage gate
   is skipped (the backend states the exact value; the out-of-vocabulary gate still applies).
2. **Wrong number after fix 1 (caught by the factual check)** — A03 was answered "FLEX-086 initial droplet diameter:
   3.07 mm" because the v3-tuned cue "how big was the droplet" fired first. The extinction cue is now checked first.
   A test pins this.

Found on holdout:

* **A34 "Which FLEX test used a propanol droplet?" — answered, judged incorrect by the reviewer.** The two claims are
  verbatim PSI-69 publication titles about propanol droplets, so they pass every deterministic check, but no FLEX
  run burned propanol and a reader could take a paper for a test. **Fixed after the holdout run, on request**: the
  fuel gate (named fuel absent from the table rows) now also applies to questions about a test or run, so these
  abstain with "no table row for fuel(s) Propanol"; questions about the publication list are still answered. Because
  the fix was made after seeing this item, the post-fix holdout figures below are **not** a held-out estimate.
* **A22 "applied", A24 "managed" — false abstentions** by the out-of-vocabulary gate (the corpus has "Managing
  centre"). Same root cause as the open v3 items G02/G06/G16: the gate needs proper stemming or a stop-word list.
* Off-target narrative claims (extra sentences from neighbouring chunks) were judged related context, not errors.

## 5. Limitations

17 holdout items: one item moves a rate by ~6 points. Labels and facts written by one developer; narrative review by
an LLM agent, not a domain expert. No LLM generator was evaluated (extractive provider), so claim support is high by
construction; A34 shows that supported claims can still mislead. Corpus is PSI-69 only by eligibility decision.

Reproduce: `cd backend && FLAMESCOPE_DENSE_BACKEND=none python scripts/eval_copilot_answers.py --split holdout --label <name>`.
