# Scientific Gates — No Unsupported Claims

## Before using a variable

Record its source definition, unit, measured/derived status, sensor or extraction method, calibration status, time basis, uncertainty, and missingness. Do not silently convert ambiguous variables.

## Comparison gate

A comparison is classified as one of:

- **Direct:** same regime and sufficiently compatible material, geometry, apparatus, conditions, measurement definition, and units.
- **Controlled variation:** same underlying setup with a clearly isolated variable change.
- **Contextual/analogous:** informative relationship, but not a controlled comparison; explain confounders.
- **Not comparable:** reject a shared quantitative ranking or axis.

FLEX droplet burning-rate constants and solid-surface flame-spread rates are not interchangeable outcomes. Cross-regime environmental comparisons may be shown only for explicitly shared, correctly defined environmental variables and must not imply a common response model.

## Modeling gate

Every model card must state:

- Scientific question and target variable.
- Source datasets and experiment-level split strategy.
- Governing equation or algorithm and source/reference.
- Assumptions, boundary conditions, and units.
- Applicability domain and out-of-domain detection.
- Baseline and validation protocol.
- Error metrics and uncertainty method.
- Failure cases and abstention conditions.

## Uncertainty gate

Use measurement uncertainty when reported; otherwise label any assumed distribution and justify it. Bootstrap at the correct independent unit (often experiment/run, not individual correlated frames). Monte Carlo requires explicit input distributions. Sobol indices require a defined model and input distributions; do not add them as decoration.

## Computer-vision gate

Lens-distortion correction is not, by itself, metric spatial calibration. Metric measurements require a documented scale and camera/sample geometry plus time calibration. Without them, report pixel-domain or dimensionless metrics only. Do not infer temperature, heat release, or soot chemistry from RGB imagery unless the measurement method supports it.

## Provenance gate

SHA-256 records file identity/integrity only. It does not establish truth, authority, or scientific validity. Retain source URL, license, retrieval date, file hash, and page/table/frame lineage.
