# 16 — Flame Vision & Metrology: FLEX HIBMS droplet images

**Handoff document.** It is written so that someone who was not in the work can continue from it.
Read section 0 first.

| | |
|---|---|
| Branches | `feat/flame-vision-metrology` (first module, commit 9f4f71f) → `feat/flame-vision-validation` (this document) |
| Method | `vision.hibms_droplet_d2_pixel` v1.0.0 |
| Status | Implemented. **Agrees with NASA's published D²(t) curves within about 3% on 3 methanol tests** (a cross-check that uses a source not yet registered). **Not validated against the tabulated K** (a definition mismatch, section 5). **No official mm calibration.** |
| Date | 2026-11-14 |

## 0. Read this first

**What this module does.** It measures the diameter of a burning droplet in NASA FLEX backlit images (pixels), fits the d²-law slope, and reports the scale-free burning rate K/D0² (1/s). It never produces millimetres.

**Where it stands.**

1. 7 FLEX tests have HIBMS images; **3 are measurable** (20CAL10, 20CAL12, 30CAL03) and **4 abstain with a recorded reason**.
2. Against the NASA table, our K/D0² is 7.0, 14.8 and 22.3% lower. **That gap is mostly explained** (section 5): the table divides by a post-ignition diameter, and we divide by the pre-ignition diameter.
3. Against the D²(t) curves that NASA **published in its report**, over the same physical window, we agree to −0.8%, +3.2% and +1.6% (worst case with digitisation error: −2.5% to +5.9%).
4. Open: why the table's K is 8–9% above NASA's own curve slope in 2 of 3 tests; NASA's real fit windows; an official pixel-to-mm scale.

**Decisions that belong to other people (not made here).**

| Decision | Owner |
|---|---|
| Register NASA/TP-2015-216046 and approve it as evidence (it is `UNREGISTERED`; the cross-check is exploratory until then) | science owner |
| Eligibility of PSI-69 (`PENDING_VERIFICATION`) | science owner |
| Whether a mm/px scale may be applied (section 6) | science owner |

**First commands for a newcomer** (section 9 has the full list):

```bash
pip install -e "backend[dev,vision]"
set FLAMESCOPE_VISION_RAW_DIR=D:\FlameScope_raw\PSI-69\calibration     (PowerShell: $env:FLAMESCOPE_VISION_RAW_DIR="...")
cd backend && pytest -q tests/vision_tests
```

## 1. NASA data used

| Item | Value |
|---|---|
| Tests with a HIBMS archive | 20CAL08, 20CAL10, 20CAL12, 30CAL02, 30CAL03, 30CAL06, 40CAL01 (PSI-69 table rows 1–8). 20CAL13 has no HIBMS archive; 30CAL07 has no bundle. |
| Images | SMD 1M60-20, 12-bit grey stored as 16-bit TIFF, **512 × 512 px (2 × 2 binned)**, 30 fps, backlit shadowgraph |
| Per test | event log `<T>.txt`, frame index `<T>A.txt`, camera settings, image archive `<T>A.zip` |
| NASA-side defects | 20CAL13 has no `A` archive; `20CAL10A_01094.tif` is truncated (flagged `unreadable_frame`) |

**Where the raw files are.** About 2.3 GB, outside git, on **`D:` only**:

| Folder | Content |
|---|---|
| `D:\FlameScope_raw\PSI-69\calibration\` | 28 files for the 7 tests |
| `D:\FlameScope_raw\PSI-69\engineering_documents\` | 3 PDFs (EIRD v4, CIR Overall Ext File, FLEX-2 ERD) |
| `D:\FlameScope_raw\NASA-TP-2015-216046\20150023456.pdf` | the NASA report (+ `pages.pkl`, `digitized_comparison.json`: scratch files from the exploration, not needed) |

Set `FLAMESCOPE_VISION_RAW_DIR` to the calibration folder (default: `<repo>/data/raw/PSI-69/calibration`). Raw data was moved from `C:` to `D:` and results were identical afterwards.

**Provenance.** `data/metadata/vision_artifact_manifest.csv` has 32 rows: file, source URL, SHA-256, size, licence, retrieval time. The script verifies SHA-256 and size before it reads a file. Archives are decoded in memory and never extracted. The files come from public PSI-69 downloads (`https://psi.nasa.gov/geode-py/ws/studies/PSI-69/download?file=<name>&version=1`, CC0-1.0) and one NTRS report.

### The NASA report (registration status)

| Field | Value |
|---|---|
| Report | NASA/TP-2015-216046 (also E-18493, GRC-E-DAA-TN5314), Dietrich et al., "Detailed Results from the Flame Extinguishment Experiment (FLEX) March 2009 to December 2011", November 2015 |
| NTRS id / URL | 20150023456 / `https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf` |
| SHA-256 / size | `b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d` / 42,900,650 bytes (matches `data/metadata/flex_report_reconciliation.json`) |
| Usage terms (NTRS metadata, read 2026-11-14) | distribution PUBLIC; copyright determination `PUBLIC_USE_PERMITTED`; not a contractor work; no third-party-permission flag |
| Registry status | **`UNREGISTERED`** (`data/metadata/source_eligibility.csv`). It is **not** in `source_registry.csv`. |
| What was done | file downloaded to `D:`; hash verified; one row in the vision manifest with licence `NTRS-PUBLIC-USE-PERMITTED` |
| What was **not** done | no registry entry, no eligibility change, no visual verification of the figures. The decision to register and approve it belongs to the science owner. |

## 2. What can be measured

| Quantity | Status | Why |
|---|---|---|
| Droplet boundary, area, equivalent diameter (px) | measured | dark round blob |
| D²(t) slope (px²/s) | measured | NASA frame timestamps |
| K/D0² (1/s) | measured, scale-free | the pixel scale cancels |
| Anything in mm | **not produced** | no approved scale (section 6) |
| Visible-flame extinction diameter | not measured | HIBMS does not see the flame; the droplet regime break is only a proxy |

## 3. Pipeline (classical, no training)

| File | What it does |
|---|---|
| `backend/app/vision/nasa_bundle.py` | parses log, index, settings; decodes frames from the zip; `raw_dir()` |
| `backend/app/vision/segmentation.py` | dark mask at f × median background (f = 0.5, the half-intensity edge); external contours; rejects shapes touching the border, elongated (aspect > 1.3) and non-round (4πA/P² < 0.7); area = filled pixel count; nearest-to-track candidate |
| `backend/app/vision/metrology.py` | per-frame records; windows; OLS fit with a Student-t CI; two-segment regime break; quality gates; diagnostics |
| `backend/app/vision/validation.py` | the pre-declared occlusion test and the uncertainty budget |
| `backend/app/vision/method_card.py`, `api.py` | method card; read-only routes (section 8) |
| `backend/scripts/run_flame_vision.py` | `fetch` and `run` |
| `backend/scripts/nasa_report_crosscheck.py` | the cross-check against the NASA report's figures (section 5) |

**Windows** are fixed a priori from NASA's event log and were never tuned to match NASA's values:

- **t = 0:** `AS Burn to Completion/Igniter On`.
- **D0:** median diameter in [`AS Needles Retract` + 0.1 s, 0).
- **Excluded:** [0, `AS Retract Completed` + 0.1 s] (igniters in view).
- **Fit:** from the end of the exclusion to the D² regime break.

**Gates.** Each one makes the module abstain and record a reason:

- a frame is unusable after a tracking jump or a diameter step > 25%;
- fewer than 3 free-droplet frames before ignition;
- fit-window coverage < 80%;
- slope ≥ 0 or R² < 0.9;
- no burning-to-evaporation break (post-break / burning slope ratio > 0.3).

Fast drift is handled by re-anchoring after 3 mutually consistent detections. Diameter jumps never re-anchor.

## 4. Results

Reproduce: `python backend/scripts/run_flame_vision.py run 20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01`.

| Test (run) | Fuel / NASA end | Result | Fit frames, R² | K/D0² ours vs table (1/s) |
|---|---|---|---|---|
| 20CAL10 (PSI-69-r002) | methanol / extinction | measured, −22.3% vs table | 136, 0.995 | 0.1348 vs 0.1734 |
| 20CAL12 (r003) | methanol / extinction | measured, −14.8% | 87, 0.993 | 0.1907 vs 0.2238 |
| 30CAL03 (r005) | methanol / extinction | measured, −7.0% | 179, 0.999 | 0.1211 vs 0.1302 |
| 20CAL08 (r001) | methanol / disruption | **abstained**: no burning-to-evaporation break (slope ratio 0.81); NASA: probably disrupted, igniter overexposed the images | — | — |
| 30CAL02 (r004) | methanol / extinction | **abstained**: droplet drifts about 46 px/s and leaves the view at 3.72 s; NASA: "leaving the HiBMs FOV one-third of the way through the burn" | — | — |
| 30CAL06 (r008) | heptane / disruption | **abstained**: tracked in 55% of the fit window; NASA: "significant sooting", drifted out of view | — | — |
| 40CAL01 (r006) | methanol / extinction | **abstained**: tracked in 74%; droplet touches the image edge at 4–6.5 s; NASA: drifted out of view and back | — | — |

NASA's own figure descriptions (report figures 5–12) agree with each abstention reason. Evidence files per test, in `data/derived/flame_vision/<T>/`: `summary.json`, `series.csv` (every frame with status), `d2_curve.svg`, `overlay.png`, `evidence.png` (original / mask / overlay, for a burning frame and an igniter-window frame). The cross-test table is `evaluation.json`.

## 5. The gap with NASA: findings

### 5.1 Confirmed

1. **Our measurement agrees with NASA's published curves.** `python backend/scripts/nasa_report_crosscheck.py` reads the red "Droplet history" markers of report figures 6, 7 and 9 (printed pages 30, 31, 33; PDF pages 36, 37, 39). It aligns the time axes on the burning-to-evaporation kink and fits NASA's curve over our fit window. Both rates are divided by their own pre-ignition plateau, so no calibration is involved:

| Test | NASA curve K/plateau | Ours | Difference | With digitisation error |
|---|---|---|---|---|
| 20CAL10 | 0.1360 | 0.1348 | −0.8% | −2.5% to +1.2% |
| 20CAL12 | 0.1848 | 0.1907 | +3.2% | +1.2% to +5.9% |
| 30CAL03 | 0.1192 | 0.1211 | +1.6% | +0.6% to +2.8% |

2. **The table's D0 is not the pre-ignition diameter.** It equals the diameter of NASA's own plot at its t = 0, after the droplet has shrunk at ignition:

| Test | Table D0 | NASA plot at t = 0 | NASA plot, pre-ignition plateau |
|---|---|---|---|
| 20CAL10 | 1.86 mm | 1.861 mm | 2.004 mm |
| 20CAL12 | 1.61 mm | 1.597 mm | 1.697 mm |
| 30CAL03 | 1.92 mm | 1.923 mm | 2.013 mm |

We normalise by the pre-ignition diameter (the plateau), the table by the post-ignition one.

3. **The gap splits exactly into three factors** (they multiply to our ratio against the table):

| Test | D0 definition | Table K vs NASA curve slope | Our measurement vs curve | Product = ours / table |
|---|---|---|---|---|
| 20CAL10 | ×0.862 | ×0.910 | ×0.992 | ×0.777 |
| 20CAL12 | ×0.900 | ×0.918 | ×1.032 | ×0.852 |
| 30CAL03 | ×0.909 | ×1.006 | ×1.016 | ×0.930 |

   The D0 definition accounts for 9–14%. Our own measurement accounts for at most 3.2%.

4. **Igniter occlusion is not the main cause** (pre-declared required-rate test, `validation.py`): only 0.17–0.30 s of NASA's implied window precedes our fit start, and closing the gap would need 3–4.6 × the fastest rate observed in the same test. This rests on one stated assumption: droplet regime break ≈ flame extinction.
5. **Not segmentation and not noise:** threshold f = 0.4–0.6 moves K/D0² by ≤ 1.3%, edge bias ±0.5 px by ≤ 1.1%, fit error 0.3–0.9%, D0 dispersion 0.3–0.8%.
6. **Tracking is stable on the 3 measured tests:** no flags in the fit windows, coverage 100%, post/burning slope ratios 0.015–0.025.
7. **The methanol rate decreases with time** (0.5 s bins: 20CAL10 0.157 → 0.118; 20CAL12 0.235 → 0.153), so any average depends on its window.

### 5.2 Not explained

1. **Why the table's K is 8–9% above NASA's own curve slope in 20CAL10 and 20CAL12** (not in 30CAL03). The report says only "linear fit of D² versus time from shortly after ignition to extinction" (Appendix A.1) with no per-test window. Windows of NASA's curve that reproduce the table K exist, but they differ per test (1.6–3.4 s, 0.3–1.4 s, 3.4–5.2 s), so they are not evidence of NASA's windows and are **not used**.
2. **A time-axis offset:** NASA's plotted time axis is about 1.1–1.4 s behind the event-log axis (1.13, 1.09, 1.36 s). It does not affect slopes. The cause is unknown.

### 5.3 Evidence needed to close it

- The per-test text files of the report (the "DVD addendum", Appendix A.1), or an answer from the PSI curators (contact published on the PSI site) on the fit windows used for the tabulated K. I could not open the PSI `Raw Data` folder (the page is too large for the browsing tool), so their absence there is **not** established.

## 6. Calibration search

| Source | What it says | Used? |
|---|---|---|
| CIR-DOC-4064 Table V (engineering documents) | HiBMs telecentric, field of view 30, 50 or 90 mm, resolution about 0.050 mm | no: design specification, does not say which field a test used |
| FLEX-2 ERD §4.1.56–57 | droplet-view field 3.0 cm, resolution 30 µm | no: a requirement, for FLEX-2 |
| **NASA/TP-2015-216046 §3.1.1 step 6** | "scale factor (32.5 pixels/mm) for most of the tests"; §3.1.2: all but the first few tests ran full-frame 1024 × 1024 | candidate only |

**Result: no official per-test pixel-to-mm calibration was found, and none is applied.** Our frames are 2 × 2 binned (512 × 512), so the report's scale would be 2 / 32.5 = **0.0615 mm/px**. That value is our arithmetic (the binning factor), not a number printed by NASA for these tests. Supporting evidence: the pre-ignition diameter converted with it matches NASA's plotted plateau to within 0.5% in all three measured tests (2.006, 1.690, 2.022 mm against 2.004, 1.697, 2.013 mm). `physical_units` stays `null` in every output until the science owner approves the source.

## 7. Uncertainty, kept separate

| Term | Value (3 tests) | Nature |
|---|---|---|
| OLS slope standard error | 0.3–0.9% (1σ) | random |
| D0 frame dispersion (1.4826 MAD) | 0.3–0.8% (1σ) | random |
| Threshold f = 0.4 / 0.5 / 0.6 | ≤ 1.3% | method sensitivity |
| Edge bias ±0.5 px | ≤ 1.1% | segmentation bias bound |
| Digitisation of NASA's figure (axis scale ±0.5%, alignment ±0.15 s) | up to ±3% on the reference | reference-side |
| Fit-window definition | not quantified | systematic; the dominant term in the comparison with the table |

**±0.5 px is the segmentation bias measured on synthetic disks. It is an edge term, not the total measurement uncertainty.** The terms are not summed. Each `summary.json` holds the `uncertainty_budget`.

**Limitations.**

- **3 of 7 tests are measurable** (all methanol). The 4 others abstain: disruption (20CAL08), drift out of view (30CAL02), soot (30CAL06) and edge contact (40CAL01).
- The earliest burning is unseen (igniters in view, about 1.5 s).
- Pixel domain only; no flame metrology (the `B`/`D` cameras were not processed).
- The cross-check uses a source that is not registered, and it assumes that the burning-to-evaporation kink is the same physical event in both curves.
- The vision results are not stored in `analysis_results` (their inputs are frames, not `measurements` rows; this needs a data-platform decision).

## 8. Integration (read-only)

| Route | Returns |
|---|---|
| `GET /api/v1/vision/method` | the method card |
| `GET /api/v1/vision/evaluation` | the cross-test table, abstentions and verdict |
| `GET /api/v1/vision/tests/{test_point}` | summary: results, `uncertainty_budget`, `comparison` (with `occlusion_assessment`), provenance with SHA-256, or the abstention reason |
| `GET /api/v1/vision/tests/{test_point}/series` | per-frame records (404 if abstained) |

`test_point` must match `^\d{2}CAL\d{2}$` (otherwise 422). The routes need neither OpenCV nor the raw files. `run_id` links to `/api/v1/runs/{run_id}` of the data platform. The cross-check file `data/derived/flame_vision/nasa_report_crosscheck.json` is not served by the API. No frontend change was made.

## 9. How to run and test

```bash
pip install -e "backend[dev,vision]"                      # vision = OpenCV + pypdfium2 (cross-check only)
set FLAMESCOPE_VISION_RAW_DIR=D:\FlameScope_raw\PSI-69\calibration
python backend/scripts/run_flame_vision.py fetch 20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01   # about 2.3 GB; retries on dropped connections
python backend/scripts/run_flame_vision.py run   20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01
set FLAMESCOPE_NASA_TP_PDF=D:\FlameScope_raw\NASA-TP-2015-216046\20150023456.pdf
python backend/scripts/nasa_report_crosscheck.py          # needs the evaluation outputs; checks the PDF SHA-256 first
cd backend && pytest -q tests/vision_tests && ruff check app scripts tests && mypy app scripts
```

Tests (`backend/tests/vision_tests/`): synthetic **test-only** disks for segmentation accuracy; verbatim NASA file excerpts for parsing; synthetic D(t) series and drift frames for the fit, the gates and re-anchoring; the pre-declared occlusion rule and the gap decomposition; real-data checks that skip without the raw files (SHA-256 against the manifest, reproducibility of stored results to 1e-12, reproducibility of the cross-check from the PDF).

The full backend suite has failures that predate this work (the 3 legacy tests and the RAG tests that need raw PSI files). On 2026-11-14 the failing set was identical to a clean copy of `release/v0.1.0-mvp` (60 entries), so these changes added none.

## 10. History of this branch

| Round | Change |
|---|---|
| First module (9f4f71f) | pipeline, 3 tests, API |
| Validation round (8a19a6e) | 4 more tests; occlusion test; re-anchoring; break-validity gate (removed a misleading +8.7% on 20CAL08); `evidence.png`; raw data to `D:`; download retries |
| This round | NASA report downloaded, hash-verified and recorded; its figure descriptions read for all 7 tests; its D²(t) figures digitised; gap explained (section 5); calibration evidence recorded; verdict text in `evaluation.json` updated |

## 11. Next steps, in order

1. **Science owner:** decide on registering NASA/TP-2015-216046 (all metadata is in section 1). Until then the cross-check stays exploratory.
2. **Ask the PSI curators** for NASA's fit windows for the tabulated K (or get the report's DVD addendum). This closes section 5.2.
3. **If the report is approved:** record the 32.5 px/mm scale (section 6) in the registry and decide whether to publish mm values with an explicit binning note.
4. Process the flame cameras (`B`/`D` archives) for extinction times, to test the "regime break = extinction" assumption behind the occlusion test.
5. Decide how to store vision results (`analysis_results` inputs are `measurements`, which frames are not).

## 12. Evidence status in outputs and the A6 audit (2026-11-14)

* **Status in every output.** `GET /api/v1/vision/evaluation` and `GET /api/v1/vision/tests/{test}` return
  `evidence_eligibility` (`{"PSI-69": "PENDING_VERIFICATION"}` today) for the sources the K/D0^2 results are derived
  from, and `reference_eligibility` (`{"NASA-TP-2015-216046": "UNREGISTERED"}`) for the report used only in the
  exploratory cross-check of section 5. Both are computed at response time from the central policy
  (`app/domain/eligibility.py`: registry status AND `data/metadata/source_eligibility.csv`), so results written
  before the fields existed carry them too and a future decision is never stale. The manifest row role
  (`reference_report`) separates the two. `run_flame_vision.py` also writes both fields into the abstention
  summaries, the evaluation and the full per-test summaries on its next run; the committed result files were not
  regenerated (it would change them only by timestamps).
* **A6 audit (`dext_origin`).** The vision pipeline never reads `dext_origin`, the enrichment file, the caption file
  or support modes; its NASA reference values (K, D0, extinction diameter, burn time) come only from the registered
  PSI-69 table through the hash-verified loader. The one place the unregistered report is read is
  `scripts/nasa_report_crosscheck.py` (its published D^2(t) curves): it labels its own output
  `UNREGISTERED ... cross-check only`, no result reads its output, and the only link is the text of the evaluation
  verdict, which already says "unregistered source". Tests pin this (the scan of vision sources, the single reader
  of the PDF, no code reading the cross-check output, both status fields). No source was registered and no
  eligibility decision changed; whether to register the report remains the science owner's decision (section 0).
  The run-level analysis A6 on `feat/integrity-gap-closure` is a separate, unchanged limitation.
