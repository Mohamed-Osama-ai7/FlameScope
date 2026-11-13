# Model Selection, Fine-Tuning and Evaluation Plan

## Retrieval

**Baseline first:** exact identifier/title search + BM25 over extracted text/tables. Preserve section/page/table metadata.

**Candidate dense model:** BGE-M3. Evaluate multilingual and technical retrieval against a small, human-reviewed query set. Candidate reranker: BGE reranker v2-M3. These are candidates, not locked choices; check model card, license, memory footprint and actual performance on the corpus.

**Hybrid tuning sequence:**
1. Build 30–50 representative questions with known supporting source spans (if the corpus supports that size).
2. Measure BM25-only, dense-only, and hybrid baselines.
3. Tune parsing/table preservation, chunk boundaries, metadata filters, fusion method/weights, Top-K and reranking.
4. Measure Recall@K, MRR/nDCG, citation-span accuracy, and retrieval latency.
5. Re-evaluate on held-out questions; report actual before/after numbers and failure cases.

## LLM / scientific copilot

Do not fine-tune the LLM as the first move. Use structured prompts, JSON schemas, source-grounded context, citation validation, and a whitelist of deterministic tools.

**Tool examples:** `search_evidence`, `get_experiment_context`, `validate_comparison`, `compute_regime_metric`, `export_evidence_brief`.

**Prompt/system tuning:** test question decomposition, evidence selection, citation placement, answer structure, abstention, tool selection, argument validation, and recovery. Score with expert-reviewed answerability, citation correctness, factual consistency, unsupported-claim rate, and tool execution correctness.

**Fine-tuning decision gate:** consider LoRA/QLoRA only if a measured, recurring failure remains after retrieval, prompt, and tool improvements, and there is a legally usable, sufficiently sized, high-quality training set. Split by investigation/run to prevent leakage. Keep a frozen held-out evaluation set. Never train the model to memorize authoritative scientific numbers; numbers must remain tool/source retrieved.

## Computer vision

Baseline with OpenCV/scikit-image for preprocessing, segmentation baselines and tracking. Consider SAM 2.1 only if it helps on the available footage and compute. Create expert-reviewed frame annotations before tuning. Evaluate Dice/IoU for masks and physical measurement error only when ground truth/calibration exists. Without metric calibration, report pixels/dimensionless measurements only.

## Scientific ML

Use scikit-learn/SciPy/Statsmodels only after verifying labels, sample independence, measurement definitions and adequate sample size. Prefer interpretable physics/statistical baselines. Tune with experiment-level grouped splits; do not split frames or repeated measurements from one run across train and test.

## Reporting rule

Targets such as Recall@5 ≥ 0.90 or Dice ≥ 0.90 are planning hypotheses, not achieved results or NASA requirements. Publish actual baseline, tuned result, dataset split, confidence interval where justified, and limitations.
