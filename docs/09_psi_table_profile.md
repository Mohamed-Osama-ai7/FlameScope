# 09 — PSI Experimental Table Profile (2026-11-13)

The three tables were downloaded with `backend/scripts/fetch_psi_table.py`. Hashes, sizes and
versions are in `data/metadata/artifact_manifest.csv`, and the column mapping is in
`data/metadata/variable_dictionary.csv`. Raw files are gitignored, so re-fetch them with the script.
This is a profile only: no value has been scientifically reviewed.

| Table | Rows | Encoding | What it contains | What it does **not** contain |
|---|---|---|---|---|
| PSI-69 FLEX (24,776 B) | 274 runs | cp1252, CRLF | Fuel (heptane 117, methanol 157); pressure (mmHg); O/N/"CO"/He mole fractions; D0; extinction diameter; "Burning rate"; burn time; end mode (extinction 186, disruption 61, completion 27); 2009-03-05 → 2011-12-08 | D(t) time series, uncertainties, apparatus variant, method used to derive the burning rate |
| PSI-25 BASS-II (16,590 B) | 129 tests | UTF-8 BOM, CRLF | 6 PI groups; free-text sample material (51 variants: PMMA, SIBAL, rods/films); flow-restrictor code; fan/air **display readings**; calibrated O₂ %vol; CO₂ %vol; CO ppm | **Flame spread rate**, flow velocity in physical units |
| PSI-98 SAFFIRE-1 (469 B) | 4 rows (2 burns, 2 flow-visualisation) | UTF-8 BOM | SIBAL fabric, 0.37 cm thick, 40.6 × 94 cm, 20 cm/s, O₂ "~21.5" %, concurrent vs opposed flow, burn time 420 s / 70 s | — (**source quarantined**) |

## Data-quality issues (kept raw; flagged, not corrected)

- **FLEX "Burning rate; mm" — RESOLVED → `burning_rate_constant_mm2_s` (mm²/s).** See the FLEX
  schema resolution section below. These are values **reported** by the FLEX team, not calculated
  by FlameScope.
- **FLEX "CO" composition — RESOLVED → `co2_mole_fraction`.** See below.
- FLEX: 34 en-dash (0x96) missing markers, 2 approximate burn times (`~6`, `~9`), duplicate
  identifier `193F001` (PSI #70 and #73, also duplicated in the report as FLEX-070/073), PSI #114 at
  0 mmHg (same value in the report; physically implausible), mixed 2- and 4-digit years, and 6 rows
  whose composition sums to more than 0.02 from 1.
- BASS-II: multi-value cells (sequences during a test), censored CO (`>500`, `over`, `OR`), 13
  negative CO ppm readings, and a `GMT` column that looks like day-of-year (unconfirmed).
- PSI-98: length and width appear swapped relative to PSI's own approach text (0.94 m × 0.4 m).
  Its content is consistent with Saffire-1, which supports the view that the title and dates are
  the metadata anomaly. The source stays quarantined.

## FLEX schema resolution (NASA/TP-2015-216046)

**Source:** NASA/TP-2015-216046 (also E-18493, GRC-E-DAA-TN5314), Dietrich, Ferkul, Bryg, Nayagam,
Hicks, Williams, Dryer, Shaw, Choi and Avedisian, *Detailed Results From the Flame Extinguishment
Experiment (FLEX) March 2009 to December 2011*, NASA Glenn Research Center, November 2015.
<https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf>. The PDF was read on
2026-11-13 (42,900,650 B, SHA-256 `b4f6ca98…c471e79d`) and is not stored in the repo. Full record:
`data/metadata/flex_report_reconciliation.json`.

| PSI raw header (unchanged) | Canonical | Unit | Evidence | Rationale |
|---|---|---|---|---|
| `Burning rate; mm` | `burning_rate_constant_mm2_s` | mm²/s | Appendix A.1 (p. 19); Table IX header (p. 20) | Appendix A.1 defines it as the average burning-rate constant from a linear fit of D² vs t, "from shortly after ignition to extinction". Table IX gives mm²/s; the PSI export lost "²/s". All 274 PSI values equal Table IX. |
| `CO initial ambient composition; mole fraction` | `co2_mole_fraction` | mole fraction | Table IX headers O2/N2/CO2/He; Appendix A.1 | Appendix A.1 defines CO2 as the ambient carbon dioxide mole fraction. The PSI export lost the subscript. |
| `O …` / `N …` | `ambient_oxygen_mole_fraction` / `ambient_nitrogen_mole_fraction` | mole fraction | Table IX; Appendix A.1 | Same subscript loss. |

The mapping lives in `backend/app/domain/flex_schema.py`, is applied on read, and is mirrored in
`variable_dictionary.csv`. Raw files and headers are untouched (a test checks the raw header bytes).

**Reported vs calculated.** `burning_rate_constant_mm2_s` is the value reported by the FLEX team,
from their own fit and window. FlameScope's d²-law output is a separate variable,
`burning_rate_constant_d2_fit_mm2_s` (`value_origin = calculated_from_diameter_history`). The
comparison gate allows the pair only as a contextual cross-check, never pooled on one axis. Table
IX is a per-test summary with **no D(t) series**, so it does **not** validate the d²-law
implementation. The report says per-test D(t) text files exist on a DVD addendum; they have not
been acquired. Reported droplet-size uncertainty is ±50 µm (sec. 3.1.2). No per-value uncertainty
is given for the burning-rate constant.

### Scope: 274 PSI records vs "first 284 tests"

- All **274/274** PSI rows match a Table IX row exactly on identifier, fuel, test end and 9
  numeric fields.
- Table IX numbering runs **FLEX-001 to FLEX-280**. *(Corrected by the audit, docs/11)*: rendering
  the pages with PDFium shows FLEX-156, 205, 213 and 228 are **numbering skips**: no row is printed
  and there is no Appendix B figure. They are not blank or unreadable rows. Table IX prints 276
  rows.
- Two text-bearing Table IX rows are **absent from PSI**: FLEX-216 (N03H201, heptane, completion)
  and FLEX-230 (H01H103, heptane, disruption).
- PSI's `FLEX Test #` is a sequential row number. It differs from the report's FLEX number for
  **119** rows (from PSI #156 = FLEX-157), so joins must use identifier + time + values. *(Corrected
  from 120; the earlier figure came from a join that collided on the duplicate identifier.)*
- **Unresolved:** 284 (abstract) vs 280 (highest Table IX number) vs 276 (printed rows) vs 274
  (PSI). The counts are not forced to agree. Why PSI omits FLEX-216/230 is a question for the PSI
  curators. The report is also internally inconsistent: Appendix A says "through December 2010",
  while the title and sec. 4.1 say December 2011.

## Consequences for the MVP

1. The **d²-law tool cannot be applied to these tables**, because they contain no D(t). It needs
   per-test diameter histories (the report's DVD text files or PSI video), or it stays unused.
2. The most direct FLEX analysis is **run-level**: how the reported burning-rate constant and
   extinction diameter vary with O₂, diluent (N₂/He/CO₂), pressure and D0, within one fuel. The
   schema now supports this; runs with test end = disruption need separate treatment.
3. BASS-II offers **no outcome variable** in its table, so it cannot support a quantitative
   comparison without the larger files.
4. FLEX comparisons now require all diluent fractions (N₂, He, CO₂/"CO") to be recorded before
   two runs can be called "direct" or a "controlled variation".
