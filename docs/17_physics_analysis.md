# 17 — Physics-informed combustion analysis (PSI-69 FLEX, reported values)

Branch `feat/physics-analysis-engine` (from `release/v0.1.0-mvp` 8180971). Code: `backend/app/analysis/physics.py`,
`backend/app/api/physics_routes.py`; method cards in `backend/app/science/method_cards.py`; tests
`backend/tests/test_physics.py`. Analysis version `physics-0.1.1`.

## 1. What the data supports (audit)

PSI-69 is a run-level table: D0, Dext, the FLEX team's reported K, burn time, pressure, composition, fuel,
end mode. There is **no D(t) series**, so no burning-rate constant can be fitted or validated here (the existing
d^2-law fitter stays "unvalidated on NASA data"). Existing analysis v0.2.0 already gives stratified Spearman
correlations. PSI-25 (excluded), PSI-98 (quarantined) and the NASA/TP report (unregistered) are not used.
Values, flags and usability come from the verified loader (`app.analysis.flex_run_level`, SHA-256 checked).

## 2. Methods

**d^2-law internal consistency** (`flex.d2_consistency_of_reported_values`). From D^2 = D0^2 − K t:
t_d2 = (D0^2 − Dext^2)/K and r = t_d2 / t_burn. Runs that end in Extinction with usable, unflagged D0, Dext, K,
burn time and D0 > Dext > 0. Uncertainty: per-run worst-case interval from each value's reporting resolution
(half a unit of the last written decimal; optional extra diameter bound); per-fuel median with percentile
bootstrap 95% CI (9999 resamples, seed 20261114). Runs whose whole interval lies outside the fuel's Tukey fences
are flagged for review. **Diagnostic only**: K is the FLEX team's fit from shortly after ignition to extinction,
D0 is at igniter-on, and the burn-time definition is not documented in the repository, so r = 1 is not expected.

**O2 association with reported K** (`flex.oxygen_effect_on_reported_k`). Within strata holding fuel, N2-only
diluent, pressure cluster and support mode fixed (the v0.2.0 strata): K = b0 + b1 X_O2, plus a sensitivity model
with D0; OLS with HC3 standard errors and Student-t 95% intervals on the residual degrees of freedom
(statsmodels). Runs need usable O2, K, D0 and ambient pressure (pressure defines the stratum). Abstains when n < 8 or fewer than 3 distinct O2 levels.
Association, not causation; support mode comes from the unregistered NASA/TP captions and is only a stratifier.

## 3. Results on the acquired data (measured 2026-11-14)

d^2 consistency: 154 of 274 runs qualify (120 excluded with counted reasons: 61 Disruption, 27 Completion, the
rest missing or flagged values). Median r: Heptane 0.949 (95% CI 0.916–0.970, n 54), Methanol 0.951
(0.941–0.957, n 100). 9 runs flagged for review, including PSI-69-r130 (FLEX-130, the short translated burn
already known from the report). Flags are for review; no value is changed.

O2 effect: 2 of 11 strata are computable. Heptane, ~1 atm, free-floating: b1 = 2.37 mm^2/s per unit mole fraction
(95% CI 1.16–3.57, n 22, R^2 0.52; D0-adjusted 2.39, 1.04–3.74). Methanol, ~1 atm, free-floating: b1 = 1.91
(1.34–2.47, n 31, R^2 0.83; D0-adjusted 1.89, 1.45–2.34). Equivalently about +0.02 mm^2/s per +0.01 in X_O2.
The other 9 strata abstain (too few runs or O2 levels). P-values are not corrected for multiple strata.

## 4. API (prefix `/api/v1`)

| Method / path | Query | Response |
|---|---|---|
| `GET /physics/d2-consistency` | `fuel` = Methanol \| Heptane (optional), `diameter_halfwidth_mm` (0 < x ≤ 1, optional) | equation, exclusions, per-fuel summary with CI, per-run t_d2, r and interval, review flags, limitations |
| `GET /physics/oxygen-effect` | `fuel` (optional) | per-stratum n, O2 range, coefficients with HC3 SE and CI, R^2, Spearman, abstentions, limitations |
| `GET /methods` | — | now also lists the two method cards above |

422 for invalid query values; 503 when the raw PSI-69 file is absent or fails its hash check, or PSI-69 is not
ACQUIRED/VERIFIED in the registry.

## 5. Gaps

* No D(t) data: K cannot be fitted or validated; extinction physics (radiative extinction, cool flames) cannot be
  analysed beyond reported Dext.
* Burn-time definition undocumented; an authoritative definition would turn the d^2 check into a sharper test.
* CO2- and He-diluted runs are not analysed for O2 effects (composition co-varies); BASS-II and SAFFIRE regimes
  are out of scope until their sources are eligible.
* The ±50 µm droplet-size uncertainty in NASA/TP-2015-216046 §3.1.2 has no defined type and the report is not
  registered, so it is offered only as an optional caller-supplied bound.

Dependencies added: `scipy>=1.13,<2.0` (bootstrap), `statsmodels>=0.14,<0.15` (OLS with HC3).

## 6. Line-ending portability of pinned artifacts (fixed 2026-11-14)

Three legacy tests failed on any fresh checkout: the v0.1.0 JSON pins and the lab dataset's embedded
`analysis_summary_sha256`/`captions_sha256` were SHA-256 values of **CRLF** working copies, while git stores and
(with `.gitattributes -text`) checks out **LF** bytes. For every affected file, SHA-256 of the committed bytes with
LF→CRLF equals the old pin exactly, so the approved content is unchanged. Fix: the artifact writers
(`run_flex_analysis.py`, `export_lab_dataset.py`, `build_flex_enrichment.py`) now write `newline="
"`, so
regeneration gives identical bytes on every OS (verified: v0.2 outputs regenerate byte-identical on Windows); the
two v0.1 JSON pins are now the committed bytes' SHA-256; the lab dataset was regenerated and only its two
provenance hash fields changed (no record, stratum or value changed). Integrity checks remain exact byte hashes.
Old clones made before `.gitattributes` keep CRLF working copies and must re-checkout those paths.
