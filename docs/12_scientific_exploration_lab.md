# 12 — Scientific Exploration Lab (v1, 2026-11-13)

An interactive exploration front end for the **approved v0.2.0 FLEX analysis** (docs 10 and 11).
It displays verified NASA-reported values and the Python-computed statistics, and it computes
nothing scientific itself. It is a research prototype, not NASA-endorsed, and not a fire-safety
tool. It has **not** been scientifically validated or reviewed by a combustion scientist.

## Run it

```bash
python backend/scripts/export_lab_dataset.py   # packages v0.2.0 -> frontend/public/data/flex_lab_dataset_v0.2.0.json
cd frontend && npm run build && npx vite preview   # or: npm run dev
npm test              # Vitest unit tests (real + synthetic data, separately)
npm run test:e2e      # Playwright: functional, axe, visual regression, performance
```

## 1. Technology decisions

| Package | Version (exact) | Licence | Role | Why |
|---|---|---|---|---|
| plotly.js-cartesian-dist-min (installed as the `plotly.js` alias) | 2.35.3 | MIT | Chart engine (SVG traces) | Interactive scientific charts with per-point `customdata` for exact record selection. The cartesian-only build is **463 KB transferred (462 KB gzip)** versus 1,418 KB for the full minified bundle; it is lazy-loaded |
| react-plotly.js | 2.6.0 | MIT | React wrapper (`factory` API) | Lets the lazy-loaded engine be injected |
| @tanstack/react-table | 8.20.6 | MIT | Observations explorer | Headless sorting/search/row identity with an accessible native `<table>` |
| vitest | 3.0.5 | MIT | Unit tests | Same Vite pipeline |
| @playwright/test | 1.49.1 | Apache-2.0 | Browser tests, screenshots | Uses the system Chrome (no browser download) |
| @axe-core/playwright (axe-core 4.10.3) | 4.10.1 | MPL-2.0 | Accessibility audit | Dev/test only; not shipped |
| @types/react-plotly.js | 2.6.3 | MIT | Types | Dev only |

**Not used, and why.**
- **D3** was not needed: Plotly covers every required chart. No hand-built chart code.
- **ECharts, Canvas, WebGL (`scattergl`)** were **not evaluated**. The real dataset has 274 records;
  SVG renders it in ≈0.7 s from page load (§7). I benchmarked only the data transformations for 5,000
  and 50,000 *synthetic* records (pure JavaScript, no rendering), not Plotly SVG rendering at those
  sizes, so there is no evidence either way for switching renderers.
- **PDF export** is not offered: output quality was not verified.

**Install notes.** The full `plotly.js` is no longer installed: the Cartesian build is the single engine through the `plotly.js` alias (see docs/13 for the audit, candidate comparison and decision). The only install scripts left in the lock file are `esbuild` (not run; build and tests work) and `fsevents` (macOS only).

Bundle (production build): app 263 KB (81 KB gzip), CSS 3 KB gzip, Plotly chunk 463 KB transferred loaded
only when a chart appears, dataset 63 KB transferred.

## 2. Architecture

```
backend/scripts/export_lab_dataset.py   Python packages v0.2.0 records, strata, rules, provenance (no new science)
frontend/public/data/flex_lab_dataset_v0.2.0.json   274 records, 137 strata, deterministic
src/lab/data/types.ts       typed dataset contract
src/lab/data/load.ts        structural validation; rejects synthetic data and wrong analysis version
src/lab/data/selectors.ts   pure filters, view definitions, eligibility, counts, quality warnings
src/lab/data/export.ts      CSV / config / summary builders (refuse synthetic data)
src/lab/charts/specs.ts     pure Plotly figure builders (no React)
src/lab/state/              LabContext (filters, selection, theme), useNarrow
src/lab/components/         Plot (lazy), ChartCard, FilterBar, EvidenceInspector, RecordTable, StrataTable, RecordList
src/lab/sections/           Overview, Combustion, Conditions, Outcomes, Quality, Observations
```

Rules kept outside React components: view definitions and eligibility (`selectors.ts`), figure
construction (`specs.ts`), exports (`export.ts`). **Eligibility is not re-derived in the browser:**
a record belongs to a view if the Python v0.2.0 strata contain it (`record.eligible`), and ρ values
are copied from the Python analysis (a backend test and a unit test both check this).

## 3. Chart catalog and interpretation rules

Every chart card states: question, variables with units, panels with n, shown/eligible/total counts,
the eligibility rule, source, exclusions by reason, limitations, and exports. Each fuel × support
mode is its own panel; support modes and fuels are never pooled.

| View | Variables | Eligibility | Reading rule |
|---|---|---|---|
| K vs O₂ (A1) | reported K (mm²/s) vs O₂ | N₂-only, valid pressure, K present | Descriptive pattern; D₀, date and pressure also vary |
| K vs pressure (A4) | K vs pressure | N₂-only at one fixed O₂ spanning ≥ 2 clusters | Only O₂ = 0.30 qualifies (n ≤ 4 per level): insufficient |
| K vs CO₂ (A2), K vs He (A3) | K vs diluent | fixed-O₂ strata with N₂-only references | **Confounded** (N₂ trades with the diluent); read per stratum |
| K vs D₀ (A5) | K vs D₀ | family × pressure cluster × support | **Unresolved / confounded** (docs/11 §5); 1/30 s-shutter sensitivity shown |
| K distributions | K per fuel × support | all with K | Box with every observation, or ECDF; no pooling; FLEX-130 retained |
| Pressure × O₂ coverage | pressure vs O₂ | valid pressure and O₂ | Coverage only; 2–3 atm records visible |
| D₀ distribution | D₀ per fuel × support | valid D₀ | Coverage only |
| Count heatmap | records per family × pressure cluster | all after visual filters | Counts only; empty cell = untested, not zero |
| Outcome by O₂ and D₀ | D₀ vs O₂, coloured by NASA test end | N₂-only | Methanol disruption is attributed by NASA to needle contamination |
| Extinction diameter vs O₂ (A6) | extinction diameter vs O₂ | Extinction end, positive, no extrapolation noted, N₂-only | Confounded by D₀; extrapolated diameters listed separately |

Not drawn: ternary or normalised composition plots (H₂O and fuel vapour are UNKNOWN, so composition
is incomplete), 3D, smoothing, confidence bands, regression lines, any predicted value.

## 4. Linked interactions and provenance

- Clicking a point (or any **Inspect** button/chip) selects the exact record by its stable
  `record_key`; the inspector opens, and the same record is highlighted as a ring in every chart
  panel that contains it and as a selected row in the table.
- Duplicate identifier `193F001` stays two records with two keys.
- Visual filters (fuel, support mode, diluent family, pressure cluster, test end, sensitivity rows)
  update all charts, the table and the CSV consistently; the filter bar shows "n of 274 pass" with
  reasons, and each chart shows **eligibility exclusions separately from visual-filter exclusions**.
  Reset restores the defaults. The default view is free-floating only.
- The **evidence inspector** (modal, focus-trapped, Esc closes and restores focus) shows: PSI row,
  FLEX number, identifier, date/GMT, test end, match method, original PSI header + raw + canonical
  value + unit + flags per variable, conditions and support basis, matrix-table cross-reference,
  quality flags with rule text, the NASA Appendix B caption, links to report pages, source URL,
  dataset version, raw / enrichment / analysis-summary / report SHA-256 and the audit doc.
- No essential information depends on hover: every chart has a "plotted records as a table" alternative.

## 5. Exports (each tested)

| Export | File | Contents | Data type label |
|---|---|---|---|
| Observations CSV | `flamescope_flex_observations_v0.2.0.csv` | filtered records: IDs, raw + canonical values, units, flags, eligibility, dataset/analysis version, SHA-256s, source URL | filtered raw observations (no calculation) |
| Chart config JSON | `flamescope_<view>_v0.2.0_config.json` | view, units, rule, limitations, filters, counts with reasons, record keys per panel, provenance | chart configuration |
| Chart SVG / PNG | `flamescope_<view>_v0.2.0.svg/.png` | the rendered chart | rendering of the plotted records |
| Analysis summary JSON | `flamescope_flex_analysis_summary_v0.2.0.json` | methodology, rules, filters, scope, all 137 strata, provenance | aggregated (Python v0.2.0) |
| Provenance JSON | `flamescope_flex_provenance_v0.2.0.json` | source, version, hashes, value origin | provenance metadata |

Export functions refuse a dataset flagged `synthetic`. SVG and PNG carry the figure only; the
matching config JSON carries provenance and filters.

## 6. Accessibility and responsive design

Light and dark themes (system preference, stored choice, toggle); categorical colours are the
validated palette slots 1–3 with shape as a redundant encoding; skip link; visible 3 px focus ring;
roles and names on controls; `aria-sort` on table headers; reduced-motion respected; panels stack
in one column on screens ≤ 700 px (found and fixed after reviewing the mobile screenshot).

## 7. Test and performance results

| Check | Result |
|---|---|
| Vitest: 35 tests (real dataset, synthetic, colour-format, plot-config and package-layout guards) | 35 passed |
| Playwright functional (13) | 13 passed |
| Playwright accessibility spec (21 tests): 17 axe-core audits (WCAG 2.0/2.1/2.2 A and AA: 6 sections × 2 themes, inspector × 2 themes, 3 mobile sections), reduced motion, focus visibility, 2 chart-geometry tests | 21 passed; **0 axe violations** |
| Playwright visual regression (9 screenshots, rerun repeatedly) | 9 passed, stable |
| Playwright performance (5) | 5 passed |
| Playwright integrity (4: duplicate 193F001, SVG/PNG integrity, console scan, no cloud button) | 4 passed |
| Playwright total (Chromium) | **52 passed**; Firefox and WebKit not completed (see docs/13 §4.5) |

Real 274-record dataset in Chrome (this machine; range over two runs; timings vary and are indicative, not guarantees):

| Measure | Value |
|---|---|
| Shell ready after navigation | 222–513 ms |
| First chart drawn after shell | 422–655 ms |
| DOMContentLoaded | 59–62 ms |
| Resources transferred (incl. Plotly) | 613 KB |
| Filter toggle → repainted (incl. a 50 ms wait) | 133–135 ms median |
| View switch → chart drawn | 459–463 ms |
| Click point → inspector open | 125–132 ms |
| JS heap with a chart open | 13–14 MB |
| CSV / SVG / PNG export | 89–98 / 79–106 / 103–115 ms |
| Sort 274 table rows / search | 175–181 / 34–48 ms |

Synthetic stress (JavaScript data transformations only, **not** browser rendering; synthetic
records never enter scientific outputs):

| Records | viewData | figure spec | CSV |
|---|---|---|---|
| 274 | 0.5 ms | 1.5 ms | 4.1 ms |
| 5,000 | 2.5 ms | 10.4 ms | 56.5 ms |
| 50,000 | 28 ms | 123 ms | 480 ms |

## 8. Limitations and open items

- Everything inherits the open questions of docs/11 (284/276/274 counts, FLEX-070/073 identity,
  FLEX-114 pressure, H₂O and fuel vapour UNKNOWN, K uncertainty UNKNOWN).
- Visual-regression baselines are generated from this build; they detect future changes, not
  whether today's rendering is correct (the screenshots were reviewed by eye, not by a designer).
- Chrome only (system Chrome via Playwright); Firefox and Safari were not tested.
- PNG/SVG exports were checked for validity and size, not pixel-by-pixel appearance.
- The page reads a static dataset; the "API" pill only reflects backend `/health`.
- ESLint is not configured.
- Needs review by a combustion scientist before any public demonstration.
