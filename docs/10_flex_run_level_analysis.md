# 10 — FLEX Run-Level Exploratory Analysis (v0.1.0, 2026-11-13)

> **Audit status (2026-11-13):** the interpretations below are **superseded by
> [docs/11_flex_scientific_audit.md](11_flex_scientific_audit.md)**. The v0.1.0 outputs in
> `reports/flex_run_level/` are kept unchanged as the approved baseline. Corrected results (support-mode
> strata, eligible extinction-diameter population, shutter and FLEX-130 sensitivities) are in
> `reports/flex_run_level_v0.2/`. Key reclassifications:
> - Obs 6 is an invalid interpretation for methanol (NASA attributes methanol disruption to needle
>   contamination).
> - Obs 4 (D0) is unresolved.
> - Obs 7 needs correction.
> - FLEX-156/205/213/228 are numbering skips, not unreadable rows.
> - The ±50 µm figure is droplet-size uncertainty, not K uncertainty.

**This is exploratory and observational.** It describes how FLEX burning-rate constants reported by
NASA relate to the recorded test conditions in the PSI-69 table. It makes no causal claims, uses no
predictive models, and has not been reviewed by a combustion scientist.

## Reproduce

```bash
python backend/scripts/run_flex_analysis.py
```

| Item | Value |
|---|---|
| Code | `backend/app/analysis/flex_run_level.py`, `backend/app/analysis/svg_charts.py`, `backend/scripts/run_flex_analysis.py` |
| Input | `data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv` (gitignored; fetch with `backend/scripts/fetch_psi_table.py PSI-69`) |
| Source | NASA PSI-69 (FLEX), DOI 10.60555/mbq8-0451, CC0-1.0; PSI file version 1, S3 version `TParjCiGvSeDqRYFafCSaXSv1jLiimyd` |
| SHA-256 | `37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96`, **verified against `artifact_manifest.csv` before parsing**; a mismatch stops the run |
| Schema | Canonical mapping `app/domain/flex_schema.py`, resolved by NASA/TP-2015-216046 Appendix A.1 / Table IX |
| Outputs | `reports/flex_run_level/`: `summary.json` (machine-readable: source URL, version, SHA-256, choices, all results), `quality_report.json`, `row_quality_table.csv` (all 274 rows plus flags), `descriptive_by_fuel.csv`, `strata_results.csv`, `charts/fig1–fig7.svg` |
| Determinism | No timestamps or randomness. A test runs the pipeline twice and checks the outputs are byte-identical |

## Scope

The analysis covers the **274 PSI rows only**. NASA/TP-2015-216046 says it reports "the first 284
tests". All 274 PSI rows match report Table IX exactly. Two Table IX rows (FLEX-216, FLEX-230) are
not in PSI, and the 284-vs-280-vs-274 difference is unresolved (`data/metadata/flex_report_reconciliation.json`).
Nothing here describes the missing tests.

## Method

- **Values are reported, not calculated.** `burning_rate_constant_mm2_s` is the FLEX team's own fit
  of D² vs t ("shortly after ignition to extinction"). The d²-law calculator is **not** called,
  because the table has no D(t). A test checks the module does not import it.
- **Fuels are never pooled.** Every stratum is one fuel. The comparison gate classified all 18,369
  methanol–heptane pairs as `contextual`, with **0 pairs allowed on a shared axis**.
- **Gas fractions are treated as compositions.** Fractions sum to about 1, so they are never used
  together as independent predictors:
  - O₂ is examined only in **N₂-only** atmospheres (CO₂ = He = 0), where O₂ is the single free
    fraction.
  - CO₂ and He are examined only at a **fixed exact O₂ value**, where the added diluent trades
    against N₂. N₂-only runs at the same O₂ and pressure cluster are included as the zero-diluent
    reference.
- **Strata:** fuel × diluent family × pressure cluster. Clusters split the sorted valid pressures
  wherever consecutive values are more than 100 mmHg apart. This is an analysis choice, not a
  physical range. Observed clusters: 526.3–544.4 (103 rows), 752–774.1 (161), 1545.7–1553.8 (2),
  2055.6–2074.2 (4), 2318.8–2319.9 (3), and 1 invalid.
- **Statistic:** Spearman rank correlation ρ with average ties, reported only for n ≥ 5. Smaller
  strata are listed with ρ = none. There are no p-values, regressions or ML; ρ describes monotonic
  association within a stratum and nothing more.
- **Comparison gate (existing rules):** used to find exact-environment replicates (same fuel,
  pressure and composition, so pairwise `direct`) and to confirm fuel separation.

## Data quality and coverage (all 274 rows retained)

| Flag | Rows | Handling |
|---|---|---|
| Missing K (blank) | 6 methanol, 10 heptane | excluded from K analyses, counted per analysis |
| Missing D0 (blank / en dash) | 3 / 9 | excluded from D0 analyses |
| Missing extinction diameter | 40 / 37 (blank or en dash) | excluded from A6; the report's "–" means no extinction |
| Zero extinction diameter | 8 heptane (none of them extinction outcomes) | flagged `zero_value_meaning_unconfirmed`; excluded from A6 if present |
| Approximate burn time (`~6`, `~9`) | 1 / 1 | value kept with `approximate` flag; burn time is not used in any correlation |
| Invalid pressure 0 mmHg | PSI #114 (methanol) | raw value kept; `invalid_nonpositive_pressure`; excluded from pressure-stratified analyses |
| Duplicate identifier `193F001` | PSI #70, #73 (heptane, same date/GMT, different values) | **both retained**; keyed by PSI row; the gate classes them as same-environment replicates (K 0.41 vs 0.56) |
| Missing GMT | PSI #9 | flagged |
| Composition sum off 1 by > 0.02 | 6 rows | flagged, not excluded (Table IX omits H₂O/fuel vapour and is rounded) |

Diluent families. Methanol: N₂-only 54, CO₂-added 75, He-added 28. Heptane: N₂-only 47, CO₂-added
48, He-added 22. Test end (both fuels): extinction 186, disruption 61, completion 27.

## Descriptive statistics by fuel (usable values)

| Variable | Methanol n · median [IQR] · range | Heptane n · median [IQR] · range |
|---|---|---|
| Reported K (mm²/s) | 151 · 0.46 [0.385–0.53] · 0.20–0.74 | 107 · 0.54 [0.435–0.635] · 0.05–1.06 |
| D0 (mm) | 154 · 3.05 [2.65–3.55] · 1.61–4.53 | 108 · 2.92 [2.41–3.44] · 1.10–4.67 |
| Extinction diameter (mm) | 117 · 1.66 [1.29–2.32] · 0.40–3.96 | 80 · 2.32 [0.705–3.00] · 0–4.60 (includes 8 flagged zeros) |
| O₂ mole fraction | 157 · 0.20 [0.16–0.21] · 0.12–0.34 | 117 · 0.20 [0.18–0.23] · 0.13–0.34 |
| Pressure (mmHg) | 156 · 759 [536–766] · 526.3–2319.7 | 117 · 760 [537–766] · 528–2319.9 |

The heptane minimum K of 0.05 mm²/s is far below the rest of that fuel's distribution. It is kept
as reported and should be checked against the report's per-test notes before anyone relies on it.

## Results (n ≥ 5 strata; all 82 strata are in `strata_results.csv`)

| Analysis | Fuel | Stratum | n | ρ |
|---|---|---|---|---|
| A1 O₂ → K | Methanol | N₂-only, 526–544 mmHg | 12 | +0.78 |
| A1 O₂ → K | Methanol | N₂-only, 752–774 mmHg | 41 | +0.82 |
| A1 O₂ → K | Heptane | N₂-only, 526–544 mmHg | 9 | +0.88 |
| A1 O₂ → K | Heptane | N₂-only, 752–774 mmHg | 32 | +0.49 |
| A2 CO₂ → K (fixed O₂) | Methanol | six strata, O₂ 0.14–0.23 | 6–15 | −0.26 to +0.30 |
| A2 CO₂ → K (fixed O₂) | Heptane | O₂ 0.18, 752–774 | 10 | −0.38 |
| A3 He → K (fixed O₂) | Methanol | five strata, O₂ 0.13–0.20 | 5–7 | +0.67 to +0.87 |
| A3 He → K (fixed O₂) | Heptane | O₂ 0.18 / 0.21, 752–774 | 6 / 17 | −0.20 / +0.17 |
| A4 pressure → K (N₂-only, O₂ 0.30) | Methanol | medians 0.635 (n=4, ~530) vs 0.68 (n=4, ~760) | 8 | 0.00 |
| A4 pressure → K (N₂-only, O₂ 0.30) | Heptane | medians 0.64 (n=4) vs 0.70 (n=3) | 7 | +0.27 |
| A5 D0 → K | Methanol | 6 family×pressure strata | 12–41 | −0.83 to 0.00 |
| A5 D0 → K | Heptane | 6 family×pressure strata | 9–32 | −0.74 to −0.28 |
| A6 O₂ → extinction D | Methanol | N₂-only, 752–774, extinction runs | 30 | −0.43 |
| A6 O₂ → extinction D | Heptane | N₂-only, 752–774, extinction runs | 14 | −0.37 |

**Replicates.** The gate found 9 groups of identical environments: 4 methanol (one of 3 runs, three
pairs) and 5 heptane pairs. The spread of reported K within a group reaches about 0.15 mm²/s
(heptane PSI #35/#229: 0.43 vs 0.57; #70/#73: 0.41 vs 0.56) while D0 also differs. This gives a
rough scale for run-to-run variation. With so few replicates, D0 cannot be studied at a fixed
environment.

**Outcomes vs conditions** (full counts in `summary.json`). Median O₂ by outcome:
- Methanol: extinction 0.18 (n=126), disruption 0.25 (n=23), completion 0.23 (n=8).
- Heptane: extinction 0.18 (n=60), disruption 0.24 (n=38), completion 0.20 (n=19).

In N₂-only atmospheres at 526–544 mmHg, most tests of both fuels ended in disruption (methanol 8/12,
heptane 8/10).

**Charts** (`reports/flex_run_level/charts/`; one panel per fuel; hover a point for its PSI row):

| Figure | Points (methanol / heptane) |
|---|---|
| fig1 K vs O₂ (N₂-only) | 53 / 41 |
| fig2 K vs CO₂ | 71 / 45 |
| fig3 K vs He | 26 / 21 |
| fig4 K vs pressure (N₂-only) | 53 / 41 |
| fig5 K vs D0 | 150 / 107 |
| fig6 extinction diameter vs O₂ | 31 / 15 |
| fig7 outcome by O₂ and D0 (N₂-only) | 53 / 41 |

The charts use palette slots 1–3, which pass the all-pairs colour-vision check (worst ΔE 9.2). Shape
is a second encoding. Aqua is below 3:1 contrast, so the CSV tables serve as the table view. The
charts are light-mode static SVG only.

## Interpretation

### Observations (what the data show)
1. In N₂-only atmospheres, reported K rises monotonically with O₂ for both fuels in both main
   pressure clusters (ρ +0.49 to +0.88, n = 9–41).
2. At fixed O₂, adding He goes with higher methanol K in all five reportable strata (ρ +0.67 to
   +0.87, n = 5–7). Heptane shows no consistent sign (n = 6, 17).
3. At fixed O₂, CO₂ shows no consistent monotonic association with K for either fuel (|ρ| ≤ 0.38).
4. Within every family×pressure stratum except one at 0.00, K is lower for larger D0 (ρ −0.02 to
   −0.83).
5. Among extinction runs, a higher O₂ goes with a smaller extinction diameter (methanol ρ −0.43, n=30;
   heptane ρ −0.37, n=14).
6. Disruption runs have higher median O₂ than extinction runs for both fuels.
7. Only one O₂ level (0.30) has N₂-only runs in both main pressure clusters, with 3–4 runs each.
   Pressure effects therefore cannot be characterised from this table.

### Hypotheses (to test, not conclusions)
- H1. Observation 1 is consistent with the expected sensitivity of droplet burning rate to ambient
  oxidiser. A physics-based comparison would need fuel properties and a cited model, which are not
  in this table.
- H2. The He association in methanol (obs. 2) could reflect helium's higher thermal diffusivity.
  The strata are small and O₂ is tied to the diluent design, so this needs dedicated runs.
- H3. Lower K at larger D0 (obs. 4) may relate to the transient behaviour and radiative losses that
  the report describes. Within strata O₂ and diluent level still vary, so D0 is confounded.
- H4. The O₂ trend in extinction diameter (obs. 5) may partly reflect D0 differences, since D0 also
  varies within the stratum.

### Limitations
- The data are observational. The test matrix was designed, not randomised, and test order and
  carry-over (the report notes accumulated CO₂ and water vapour) are not modelled.
- K is the FLEX team's average over a test-specific window. Fit windows differ (the report notes
  extrapolation when a droplet left the field of view), and there is no per-value uncertainty.
  Droplet size uncertainty is ±50 µm.
- Strata are small (often n = 5–12). ρ has no confidence interval and no multiple-comparison control.
- Pressure clusters are an analysis grouping; pressure still varies within a cluster.
- The table lacks H₂O and fuel-vapour fractions (Appendix A lists them; PSI omitted them), fibre or
  free-floating status, and the per-test notes.
- These results cover 274 of the 284 tests NASA reports; the missing tests could change stratum
  statistics.
- No result here is an operational fire-safety limit.
