# 11 — Scientific Audit of the FLEX Run-Level Analysis (2026-11-13)

**Status:** this is an internal audit by the build team, **not independent scientific validation**.
Where the evidence is insufficient, the result is UNKNOWN.

## Sources and integrity

| Item | Check | Result |
|---|---|---|
| PSI-69 table | SHA-256 recomputed against `artifact_manifest.csv` | `37c88ce8…7e1b96`, matches; raw file unchanged |
| NASA/TP-2015-216046 PDF | SHA-256 | `b4f6ca98…c471e79d`, matches the recorded hash (not stored in the repo) |
| Report text | pypdf 7.0.1 text extraction (scratch install) | used for parsing |
| Report pages | **Visual check**: Table IX pp. 26, 28–32 rendered with PDFium (pypdfium2, scratch install) | see the reconciliation section |
| Approved v0.1.0 outputs | SHA-256 recorded in `tests/test_flex_audit.py` | unchanged (test enforced) |

## 1. Findings (read-only audit)

| # | Existing implementation | Source evidence | Risk | Correction | Resolvable? |
|---|---|---|---|---|---|
| F1 | Fiber-supported and free-floating droplets pooled in every stratum and chart | §2.1: fiber tests use an 80-µm fiber, some translated to create subbuoyant flow; Appendix B captions state the support mode for every test | **High.** Different flow regimes. In v0.2, heptane O₂→K is ρ −0.89 (n=5) in fiber runs vs +0.71 in free-floating runs | Support mode taken from the captions (enrichment); every stratum split by support mode; primary charts free-floating only | Yes for 274 rows. Translation is stated for 30 fiber runs; 33 fiber runs have translation "not stated"; 2 rows have conflicting sources (FLEX-053, FLEX-124) |
| F2 | FLEX-001..009 treated like all other runs | §4: shutter 1/30 s until FLEX-009, igniter glow distorts droplet size at ignition; FLEX-001 caption says the diameter "could not be measured accurately" during ignition | **Medium–high** for D0. Methanol D0→K (N₂-only, ~1 atm, free-floating): ρ −0.29 with these rows, **+0.08 without** | Tagged `shutter_1_30s_period`; ρ reported with and without them | Partly. The effect on Table IX D0 and K is not quantified by NASA |
| F3 | No contamination handling | §5.2: **all** tests in the report used coated needles. NASA says K and flame size were "minimally influenced", methanol disruptive extinction is "probably due" to the contaminant, and no conclusion can be drawn on heptane disruption. Captions name FLEX-088 (probable) and FLEX-109 (possible); "sparklers" in FLEX-037 and 090 | **High** for outcome interpretation, low for K (per NASA) | Report-wide `coated_needle_period`; only the 4 documented tests flagged; outcome tables carry NASA's caveats | Only as far as NASA states. Other affected tests (NASA: "approximately four" distorted methanol droplets) are not identified |
| F4 | Missing extinction diameter treated as missing, zeros excluded | App. A.1: "–" means no extinction (completion or disruption); not listed means insufficient HiBMs view; some values extrapolated | **High.** Several meanings were conflated | `dext_origin` with 9 categories; A6 restricted to Extinction + positive value + no extrapolation noted | Mostly. 5 methanol rows have "–" with test end Extinction (inconsistent in the source); zero and non-extinction values have unclear meaning (left unresolved) |
| F5 | Pressure clusters from a 100 mmHg gap rule | Report design levels 0.70, 1.0, 2.03, 2.7, 3.05 atm (§1, Tables I–VIII) | Low. The rule looked arbitrary | Clusters are identical for gaps of 25–200 mmHg (test enforced) and labelled with NASA nominal levels | Yes |
| F6 | FLEX-114 pressure 0 mmHg excluded | Table VI lists FLEX-114 at 0.70 atm and its caption says "0.70-atm"; Table IX says 0 | Low | Conflict recorded in the enrichment; **not substituted**; still excluded from pressure-stratified analyses | Unresolved source conflict (the report contradicts itself) |
| F7 | Duplicate 193F001 treated as two replicates (K 0.41 vs 0.56) | Table IX FLEX-070 and 073 share identifier and GMT; Table V D0 1.30 vs 4.72 mm; captions describe different events | **Medium.** The "replicate spread" example rests on an ambiguous identity | Stable `record_key`; both rows kept; replicate claim downgraded | **No.** Which row belongs to which test is unknown |
| F8 | "120 rows" PSI-number ≠ report number | Exact join | Low | Corrected to **119** | Yes |
| F9 | "4 rows without extractable text" | Visual check | Medium (scope) | FLEX-156/205/213/228 are **numbering skips**: no row printed, no figure | Yes |
| F10 | CO₂/He at fixed O₂ called a compositional isolation | Mixture: N₂ is the balance; Table IX omits H₂O and fuel vapour (A.1 defines them; Table IX has no such columns); reference runs come from other test days | Medium | Notes and docs mark these as **confounded comparisons**, not controlled ones | No; H₂O/fuel vapour are not in Table IX or PSI |
| F11 | Heptane K = 0.05 "to be checked" | Table IX FLEX-130 printed .05 (visual check); caption: fiber-supported, translating 3 mm/s, very short burn, radiative extinction soon after translation began | Low | Retained; labelled sensitivity | Yes. Confirmed as reported |
| F12 | ±50 µm uncertainty | §3.1.2: droplet-size uncertainty. NASA gives no uncertainty for K | — | Documentation now states explicitly that ±50 µm is **not** a K uncertainty | Yes (K uncertainty UNKNOWN) |
| F13 | Two "D0" quantities | Matrix Tables I–VIII "Initial droplet diameter" differs from Table IX "Actual D0" (at igniter-on). For example, FLEX-001: 1.80 vs 1.69 | Low | Analysis uses Table IX D0 (= PSI) only | The definition of the matrix D0 is not stated |
| F14 | v0.1 subtitles and footnotes would overflow when lengthened | Visual check | Low | Text wraps; n and exclusions stated in each chart | Yes |

## 2. Source-to-data reconciliation (counts not forced)

| Quantity | Value | Evidence |
|---|---|---|
| Tests stated in the abstract | 284 | p. 1 |
| Table IX numbering | FLEX-001 … FLEX-280 | visual |
| Table IX printed rows | **276** | visual; 156, 205, 213, 228 not printed |
| Appendix B figures | 276 (one per printed row) | caption parse |
| PSI-69 rows | 274; all value-identical to a Table IX row | exact 12-field join |
| In Table IX, not in PSI | FLEX-216 (N03H201), FLEX-230 (H01H103) | visual |
| FLEX-156 | listed in matrix Table VIII, no Table IX row, no figure | text and visual |
| Date coverage | Appendix A intro says "through December 2010"; title, §4.1 and dated rows reach 2011-12-08 | text |

**Unresolved:** 284 − 276 = 8 tests that the report counts but does not print. The reason is not
stated.

Stable record key: `PSI69-r{row}|FLEX-{n}|{identifier}|{date}|{GMT}`, in
`data/derived/flex_enrichment_v1.csv`.

## 3. Variable coverage

| Field | App. A.1 defines | Table IX prints | PSI-69 | Recovered (enrichment v1) |
|---|---|---|---|---|
| FLEX test number | ✔ | ✔ | sequential row no. (≠ for 119 rows) | ✔ `flex_test_number` (exact join) |
| Identifier, date, GMT, fuel | ✔ | ✔ | ✔ | — |
| Pressure (mmHg) | ✔ ("P—absolute") | ✔ | ✔ | matrix-table atm for 152 tests (agree within 0.009 atm except FLEX-114) |
| O₂, N₂, CO₂, He | O₂, CO₂, N₂ defined; He in table only | ✔ | ✔ (headers lost subscripts) | — |
| **H₂O mole fraction** | ✔ | ✘ | ✘ | **UNKNOWN** (the report says the electronic data exist; not acquired) |
| **Heptane / methanol vapour** | ✔ | ✘ | ✘ | **UNKNOWN** |
| **Fiber** | ✔ | ✘ | ✘ | ✔ caption for 274 rows; matrix Yes/No for tests ≤166 |
| Translation | §2.1 | ✘ | ✘ | stated for 30 rows; otherwise "not stated" |
| **Notes** | ✔ | ✘ (no notes column printed) | ✘ | caption text (`flex_enrichment_v1_captions.json`) plus flags |
| D0 (igniter-on), Dext, K (mm²/s), burn time, test end | ✔ | ✔ | ✔ | Dext origin from A.1 and captions |

## 4. Pressure distribution (both fuels, all rows)

- Valid range 526.3–2319.9 mmHg (0.69–3.05 atm). One invalid record: FLEX-114 at 0 mmHg (conflict
  above).
- Clusters (rows): ~0.7 atm 526.3–544.4 (103); ~1 atm 752–774.1 (161); ~2.03 atm 1545.7–1553.8 (2);
  ~2.72 atm 2055.6–2074.2 (4); ~3.05 atm 2318.8–2319.9 (3). Counts by fuel × family are in
  `summary.json → quality.pressure_distribution`.
- **All 9 records above 1000 mmHg** share one composition, O₂/N₂/CO₂ = 0.21/0.09/0.70 (Table II,
  free-floating). Reported K exists for methanol at 3.05 atm (0.37, 0.40) and 2.72 atm (0.49, 0.53),
  and for heptane at 2.03 atm (0.61). This is the only fixed-composition pressure series; n = 2 per
  level is **insufficient**.
- v0.1 did not silently drop these records: they appeared in fig. 2 and fig. 5 and in n < 5 strata.
  But doc 10's "pressure cannot be characterised" omitted that this series exists.

## 5. D0 vs reported K

- There are few exact-environment replicates (9 gate-`direct` groups, and one of them is the
  ambiguous FLEX-070/073 pair).
- Within free-floating strata, ρ ranges from −0.82 to +0.21. The largest stratum (methanol N₂-only
  ~1 atm, n=31) goes from −0.29 to **+0.08** when the 1/30-s-shutter rows are removed.
- O₂, diluent level, test chronology, H₂O and fuel vapour (unavailable) vary within strata.
- **Assessment: UNRESOLVED / confounded.** No D0 effect on K can be isolated from this table. No
  multivariable model was fitted, because doing so would not remove the unmeasured confounders.

## 6. Heptane K = 0.05 mm²/s

PSI #130 = FLEX-130, C13H201, 9/17/2010 03:55:59, heptane, 537.2 mmHg, O₂/N₂/CO₂ 0.17/0.38/0.45,
D0 2.91, Dext 2.89, burn time 0.6 s, Extinction. It is identical in PSI and in the rendered Table IX
(p. 29).

The caption reads: fiber-supported, **translating 3 mm/s**, "very short burn", radiative extinction
"very soon after translation began".

**Verified as reported.** The value is retained. NASA documents no error; the context is a very
short, convectively disturbed burn. It sits only in fiber-translated strata and never in a
free-floating result.

Sensitivity: heptane K over all rows has n=107, median 0.54, SD 0.161; without FLEX-130, n=106,
median 0.54, SD 0.154.

## 7. Extinction diameter and outcomes

`dext_origin` counts:

| Category | Methanol | Heptane |
|---|---|---|
| Reported, no extrapolation noted | 84 | 54 |
| Extrapolation noted in caption | 19 | 2 |
| Not listed (insufficient view, A.1) | 24 | 25 |
| "–" = no extinction (completion/disruption) | 11 | 12 |
| "–" with test end Extinction (inconsistent) | 5 | 0 |
| Value with non-extinction end (meaning unclear) | 14 | 16 |
| Zero (meaning unconfirmed) | 0 | 8 |

A6 now uses only the first category:
- Methanol N₂-only ~1 atm free-floating: n=19, ρ −0.58.
- Heptane: n=10, ρ −0.33.

D0 varies within these strata and Dext depends on D0, so this is **confounded**.

**Outcomes:** methanol disruption is attributed by NASA to the contaminant ("probably"). Disruption
counts versus conditions **must not be interpreted as an environmental response** for methanol. For
heptane NASA states no conclusion can be drawn.

## 8. Fiber, contamination and measurement quality

- **Support mode:**
  - Methanol: free-floating 121, fiber translated 17, fiber translation not stated 18, conflicting 1.
  - Heptane: free-floating 88, fiber translated 13, fiber translation not stated 15, conflicting 1.
- **Contamination:** a report-wide coated-needle condition. Specific tests flagged only where NASA
  names them (FLEX-037, 088, 090, 109). No clean/contaminated status is inferred for the others.
- **Shutter:** FLEX-001..009 tagged and run as a labelled sensitivity. Neither the shutter rows nor
  any contamination-flagged row are removed from the primary results.

## 9. Statistics and corrected interpretation

- v0.2 has **137 strata, of which 38 report ρ**. Every one is in
  `reports/flex_run_level_v0.2/strata_results.csv` with exact n, fuel, stratum definition, tie
  counts, sensitivity rows and ρ without them; exclusions by reason are in `summary.json`.
- ρ is **descriptive only**. n ≥ 5 is a reporting floor, not reliability. There are no p-values,
  confidence intervals or significance claims, and no multiple-comparison correction.
- Replicates are kept. Repeated runs on one test day share chamber gas and carry-over, so they are
  not assumed independent. Video frames are never used.

### Classification of the doc 10 (v0.1) conclusions

| v0.1 statement | Class |
|---|---|
| K values, units and definitions as reported | 1. Directly supported by verified source data |
| Obs 1: K rises with O₂ in N₂-only atmospheres | 2. Descriptive exploratory. It holds in every free-floating stratum (methanol ρ +0.72 n=7 and +0.89 n=31 (+0.84 without shutter rows); heptane +0.97 n=5 and +0.71 n=23) but not in one fiber stratum (heptane −0.89, n=5). D0 and test sequence also vary |
| Obs 2: He goes with higher methanol K | 3/4. Potentially confounded (N₂ trades with He) and insufficient (two free-floating strata, n=6 each) |
| Obs 3: no consistent CO₂ association | 4. Insufficient. One stratum flips sign with the shutter sensitivity (−0.32 → +0.07) |
| Obs 4: larger D0 goes with lower K | 3. Potentially confounded; **unresolved** (see section 5) |
| Obs 5: higher O₂ goes with smaller extinction diameter | 3. Potentially confounded (D0); eligible population now explicit |
| Obs 6: disruption at higher O₂ | **5. Invalid interpretation for methanol** (NASA attributes disruption to contamination); 6. Unresolved for heptane |
| Obs 7: pressure cannot be characterised | 5. Requires correction: one fixed-composition 2.03–3.05 atm series exists but is insufficient (n ≤ 2 per level) |
| Replicate K spread "about 0.15 mm²/s" | 3. Its largest example (FLEX-070/073) has an unresolved identity |
| H1–H4 | Hypotheses only; not conclusions |

No result from this dataset is a spacecraft fire-safety limit or an operational recommendation.

## 10. Changes made

| File | Change | Why |
|---|---|---|
| `backend/scripts/build_flex_enrichment.py` (new) | Deterministic, hash-checked extraction of the enrichment from the report | F1–F9, F13 |
| `data/derived/flex_enrichment_v1.csv` (new, SHA-256 `fd929d6f…`) and `…_captions.json` | Per-row record key, FLEX number, support mode, matrix fiber/pressure, conflicts, shutter/contamination flags, Dext caption note; full captions (public domain) | Provenance-linked enrichment; raw PSI untouched |
| `app/analysis/flex_run_level.py` | `attach_enrichment`, `classify_dext`, support-mode strata, eligible A6 population, ties, labelled sensitivity, nominal-level labels, pressure distribution, contamination caveats | F1–F7 |
| `app/analysis/svg_charts.py` | Wrapped subtitle and footnote | F14 |
| `backend/scripts/run_flex_analysis.py` | v0.2.0 → `reports/flex_run_level_v0.2/`; free-floating primary charts listing excluded counts; plotted record keys; K-by-support-mode; FLEX-130 sensitivity; multiple-comparison statement | F1, F11 |
| `data/metadata/flex_report_reconciliation.json`, `docs/09` | 119 (not 120); visual verification of skipped numbers; new unresolved items | F8, F9 |
| `backend/tests/test_flex_audit.py` (new) | 25 tests for every corrected behaviour, including v0.1 output hashes | Phase 6 |

The v0.1.0 outputs (`reports/flex_run_level/`) are kept byte-identical. They were produced by the
v0.1.0 code, and current code writes only to `reports/flex_run_level_v0.2/`.

## 11. Unresolved scientific questions

1. Why 284 tests are counted but 276 printed, and why PSI omits FLEX-216 and FLEX-230.
2. The identity of the FLEX-070/073 rows (shared identifier and GMT).
3. FLEX-114 pressure: 0 mmHg (Table IX) vs 0.70 atm (Table VI and caption).
4. The meaning of zero, "–"-with-Extinction, and non-extinction diameter values.
5. H₂O and fuel-vapour mole fractions, needed for a complete composition (UNKNOWN).
6. Translation status of 33 fiber runs; support conflicts for FLEX-053 and FLEX-124.
7. How large the shutter effect is on Table IX D0 and K for FLEX-001..009.
8. Which of the "approximately four" distorted methanol droplets are affected.
9. Uncertainty of the reported K (not given).

## 12. Suitability

**Suitable only for a cautious exploratory demonstration** of provenance, data-quality handling
and regime-aware comparison, with these limits:
- free-floating K vs O₂ shown as a descriptive pattern;
- the caveats above displayed alongside;
- no causal, predictive or safety language;
- D0, CO₂, He, pressure and outcome relationships presented as unresolved or confounded.
