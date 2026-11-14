# 16 — Flame Vision & Metrology: FLEX HIBMS droplet images

Branches:

- `feat/flame-vision-metrology`: first module, commit 9f4f71f.
- `feat/flame-vision-validation`: validation round, this document.

Method `vision.hibms_droplet_d2_pixel` v1.0.0. Status: **implemented and compared with NASA-reported values; not validated** (section 5). Status date: 2026-11-14.

## 1. Audit: NASA data used

| Finding | Evidence |
|---|---|
| PSI-69 (FLEX, about 860 GB) has a `Calibration` folder with bundles for FLEX table rows 1–9. Each bundle holds an event log, a per-camera frame index, camera settings and image archives (`A` = HIBMS backlit droplet, 30 fps). | PSI-69 page, "Data files and documents" |
| HIBMS frames: SMD 1M60-20 camera, 12-bit grey stored as 16-bit TIFF, 512 × 512 px (2 × 2 binned), 30 fps. | `<T>_HIBMS_Camera_Settings.txt` |
| All 7 bundles with a HIBMS archive were processed: 20CAL08, 20CAL10, 20CAL12, 30CAL02, 30CAL03, 30CAL06, 40CAL01 (rows r001–r008; 20CAL13 has no HIBMS archive, 30CAL07 has no bundle). | section 4 |
| NASA-side defects: 20CAL13 has no `A` archive and its readme lists missing frames; `20CAL10A_01094.tif` is truncated (flagged `unreadable_frame`). | readme; decoder error |
| **No per-test spatial calibration (mm/px) exists in any calibration or engineering file** (section 6). | all files listed below |

**Raw-data location.** About 2.3 GB, outside git, on `D:` only: `D:\FlameScope_raw\PSI-69\calibration\` (28 files) and `D:\FlameScope_raw\PSI-69\engineering_documents\` (3 PDFs). Set `FLAMESCOPE_VISION_RAW_DIR` to the calibration folder. Every file is recorded in `data/metadata/vision_artifact_manifest.csv` (31 rows) with its source URL, SHA-256, size, licence (CC0-1.0) and retrieval time. The script verifies SHA-256 and size before it reads anything. Archives are decoded in memory and never extracted. All files are public PSI-69 files (`https://psi.nasa.gov/geode-py/ws/studies/PSI-69/download?file=<name>&version=1`). PSI-69 eligibility (`PENDING_VERIFICATION`) is unchanged.

## 2. Feasibility

| Quantity | Status | Why |
|---|---|---|
| Droplet boundary, area, equivalent diameter (px) | measured | dark round blob in backlit view |
| D²(t) slope (px²/s) | measured | NASA per-frame timestamps |
| K/D0² (1/s) | measured, scale-free | pixel scale cancels; comparable with NASA's reported K/D0² |
| Anything in mm | **not produced** | no per-test mm/px calibration (section 6) |
| Visible-flame extinction diameter | not measured | HIBMS does not see the flame; the droplet regime break is a proxy |

## 3. Pipeline (classical, no training)

| File | What it does |
|---|---|
| `nasa_bundle.py` | parses the event log, frame index and camera settings; decodes frames from the zip; `raw_dir()` |
| `segmentation.py` | dark mask at f × median background (f = 0.5, the half-intensity edge); external contours; rejects shapes touching the border, elongated shapes (aspect > 1.3) and non-round shapes (4πA/P² < 0.7); area = filled pixel count; nearest-to-track candidate |
| `metrology.py` | per-frame records; windows; OLS with a Student-t CI; two-segment regime break; quality gates; diagnostics |
| `validation.py` | the pre-declared occlusion test and the uncertainty budget (section 9) |
| `method_card.py`, `api.py` | method card and read-only routes |

**Windows**, fixed a priori from NASA's event log and unchanged in the validation round:

- **t = 0:** `AS Burn to Completion/Igniter On`.
- **D0:** median diameter in [`AS Needles Retract` + 0.1 s, 0).
- **Excluded:** [0, `AS Retract Completed` + 0.1 s], igniters in view.
- **Fit:** from the end of the exclusion to the D² regime break.

**Gates.** Each gate makes the module abstain (a reason is recorded); none produces a value:

- a frame is unusable after a tracking jump or a diameter step > 25%;
- fewer than 3 free-droplet frames before ignition;
- fit-window coverage < 80%;
- slope ≥ 0 or R² < 0.9;
- **(new)** no burning-to-evaporation break: post-break slope / burning slope > 0.3.

## 4. Results, before and after the validation round

Reproduce with `python backend/scripts/run_flame_vision.py run 20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01`.

| Test (PSI-69 run) | Fuel / NASA end | Before (9f4f71f, or first run) | After (this branch) | Fit frames, R² | K/D0² vision vs NASA (1/s) |
|---|---|---|---|---|---|
| 20CAL10 (r002) | methanol / extinction | −22.3% | −22.3% (unchanged) | 136, 0.995 | 0.1348 vs 0.1734 |
| 20CAL12 (r003) | methanol / extinction | −14.8% | −14.8% (unchanged) | 87, 0.993 | 0.1907 vs 0.2238 |
| 30CAL03 (r005) | methanol / extinction | not run | **−7.0%** | 179, 0.999 | 0.1211 vs 0.1302 |
| 20CAL08 (r001) | methanol / disruption | +8.7% (invalid window 1.53–2.73 s) | **abstained**: no burning-to-evaporation break (slope ratio 0.81); disruption at about 5.3 s | — | — |
| 30CAL02 (r004) | methanol / extinction | abstained (tracking cascade) | **abstained**: droplet drifts about 46 px/s and leaves the view at 3.72 s, before extinction (NASA burn 7.64 s) | — | — |
| 30CAL06 (r008) | heptane / disruption | abstained | **abstained**: tracked in 55% of the fit window (soot obscures the droplet) | — | — |
| 40CAL01 (r006) | methanol / extinction | not run | **abstained**: tracked in 74% (droplet touches the image edge 4–6.5 s) | — | — |

On the 3 measurable tests, the vision K/D0² is below NASA by **7–22%** (mean −14.7%). The gap varies from test to test, so it is not a constant offset. The implied scale (NASA D0 / measured D0_px; a consistency check, never used) is 0.0571–0.0586 mm/px, a spread of 2.6%.

Evidence per test is in `data/derived/flame_vision/<T>/`:

| File | Content |
|---|---|
| `d2_curve.svg` | burning curve |
| `overlay.png` | contour at 3 times |
| `evidence.png` | original / mask / overlay, for a burning frame and for a frame inside the igniter window |
| `series.csv` | every frame with status and flags |
| `summary.json` | the full summary |

The cross-test table is `evaluation.json`.

## 5. Investigation of the gap: confirmed vs hypotheses

**Confirmed (from data):**

1. **Igniters are not the main cause.** The occlusion is real: `evidence.png` shows a partly covered, irregular droplet at about 0.6–1.2 s. It is short, however (about 0.6 s with no clean droplet). Implied ignition is t_break − NASA burn time, at 1.23, 1.33 and 1.55 s. Only 0.30, 0.20 and 0.17 s of NASA's implied window lie before our fit start. To close the gap, that hidden part would need K/D0² = 0.78, 0.72 and 0.46 1/s, which is 3–4.6 × the fastest rate observed anywhere in the same test (0.17, 0.23, 0.15). Verdict: **rejected as main cause** for all 3 tests. This rests on one stated assumption: droplet regime break ≈ flame extinction.
2. **Not segmentation and not noise.** Threshold f = 0.4–0.6 changes K/D0² by ≤ 1.3%; an edge bias of ±0.5 px by ≤ 1.1%; the fit standard error is 0.3–0.9%; D0 dispersion 0.3–0.8%. Together these are far below 7–22%.
3. **Tracking is stable on the measured tests.** There are no tracking or diameter flags in any fit window (coverage 100%). The regime breaks are clear: post/burning slope ratios 0.015–0.025.
4. **The rate decreases with time for methanol.** In 0.5 s bins, 20CAL10 goes from 0.157 to 0.118 and 20CAL12 from 0.235 to 0.153. The average therefore depends strongly on the exact window, which is known physics (water absorption; Hicks et al. in PSI-69 publications).

**Hypotheses (not tested here):**

1. NASA's per-test fit windows ("shortly after ignition to extinction", NASA/TP-2015-216046 App. A.1) differ from ours. Given (4), this alone could move K/D0² by tens of percent.
2. The droplet regime break lags or leads visible-flame extinction. The flame cameras (`B`/`D` archives) or the radiometer would settle this. The radiometer file was inspected, but its clock offset relative to the image clock (≈ 1 s, status sampled at 1 Hz) is too large to time ignition, so it is not used.
3. NASA D0 uncertainty (±50 µm ⇒ ±5% in K/D0²) and edge-definition differences between NASA's image analysis and ours.

## 6. Calibration search (P1)

The 3 PSI-69 engineering documents were read:

- EIRD v4;
- the CIR Payload Accommodations Handbook extract (CIR-DOC-4064);
- the FLEX-2 Engineering Requirements Document.

| Document | What it states | Calibration? |
|---|---|---|
| CIR-DOC-4064 Table V | HiBMs: telecentric, FOV **30, 50 & 90 mm diameter** (selectable), ~0.050 mm resolution at 1024 × 1024, 512 × 512 binned | design specification; does not say which FOV each FLEX test used |
| FLEX-2 ERD §4.1.56–57 | droplet view FOV **3.0 cm diameter**, spatial resolution 30 µm | a requirement, and for FLEX-2, not FLEX |

**No official per-test pixel-to-mm calibration was found.** For comparison only: a 30 mm field across 512 px would be about 0.0586 mm/px, which agrees with the implied scale (0.0571–0.0586) to within 2.6%. This supports a fixed magnification but is **not** an official scale and is not used.

## 7. Uncertainty, kept separate

Each `summary.json` has an `uncertainty_budget` (relative to K/D0²):

| Term | Value (3 tests) | Nature |
|---|---|---|
| OLS slope standard error | 0.3–0.9% (1σ) | random |
| D0 frame dispersion (1.4826 MAD) | 0.3–0.8% (1σ) | random |
| Threshold f 0.4 / 0.5 / 0.6 | ≤ 1.3% | method sensitivity |
| Edge bias ±0.5 px | ≤ 1.1% | segmentation bias bound |
| Fit-window definition | not quantified | systematic, likely dominant (section 5) |

The **±0.5 px** figure is the segmentation bias measured on synthetic disks (an edge term). It is **not** the total measurement uncertainty.

## 8. Integration

| Route | Returns |
|---|---|
| `GET /api/v1/vision/method` | the method card |
| `GET /api/v1/vision/evaluation` | the cross-test table |
| `GET /api/v1/vision/tests/{test_point}` | one test's summary, including `uncertainty_budget`, `comparison.occlusion_assessment`, provenance with SHA-256, or the abstention reason |
| `GET /api/v1/vision/tests/{test_point}/series` | per-frame records |

These routes are read-only and need neither OpenCV nor the raw files. `run_id` links to the data-platform `/api/v1/runs/{run_id}`. No frontend change was made.

## 9. Validation-round changes

None of these changes alters a window or targets NASA's values. The before/after table is in section 4.

1. **Raw data on D:.** `FLAMESCOPE_VISION_RAW_DIR` sets the location, and results were identical after the move.
2. **Downloads retry** after dropped connections (`IncompleteRead`); a partial body is never stored.
3. **Re-anchoring.** Three consecutive detections that agree with each other in position (diameter step already ≤ 25%) move a stale track anchor. A drifting droplet can travel more than the anchor allows across the igniter gap (30CAL02). Diameter jumps (debris, soot) never re-anchor. Earlier results are unchanged.
4. **Break-validity gate.** A post-break / burning slope ratio ≤ 0.3 is required. Without it, 20CAL08 (disruption, no evaporation tail) was cut at 2.73 s and reported a misleading +8.7%. Measured tests show 0.015–0.025 and 20CAL08 shows 0.81, so the threshold has a wide margin.
5. **Diagnostics** (no effect on results):
   - clean frames inside the igniter window and the physically hidden interval;
   - local 0.5 s rates;
   - the ±0.5 px edge-bias refit;
   - the pre-declared required-rate occlusion test (`app/vision/validation.py`);
   - `evidence.png`.

Commands:

```bash
pip install -e "backend[dev,vision]"
set FLAMESCOPE_VISION_RAW_DIR=D:\FlameScope_raw\PSI-69\calibration        (PowerShell: $env:...)
python backend/scripts/run_flame_vision.py fetch 20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01
python backend/scripts/run_flame_vision.py run   20CAL08 20CAL10 20CAL12 30CAL02 30CAL03 30CAL06 40CAL01
cd backend && pytest -q tests/vision_tests
```

## 10. Remaining gaps and blockers

1. **No per-test mm/px calibration.** Physical metrology stays blocked.
2. **Not validated.** The 7–22% gap is unexplained. The next evidence would be NASA's fit windows or D²(t) histories (NASA/TP-2015-216046 is `UNREGISTERED`; registering it is the science owner's decision), or flame-camera extinction times from the `B`/`D` archives.
3. **Coverage.** Only 3 of 7 tests are measurable with this method: disruption, drift out of view, edge contact and soot.
4. **No flame metrology.** Nothing yet from the `B`/`D` cameras, and the results are not stored in `analysis_results` (needs a data-platform decision on frame artifacts).
