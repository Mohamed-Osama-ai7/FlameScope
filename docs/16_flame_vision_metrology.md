# 16 — Flame Vision & Metrology (first module): FLEX HIBMS droplet images

Branch `feat/flame-vision-metrology` (from `release/v0.1.0-mvp`). Status date: 2026-11-14.
Method `vision.hibms_droplet_d2_pixel` v1.0.0. Status: **implemented and compared with NASA-reported
values; not validated** (section 5).

## 1. Audit: what NASA data exists

| Finding | Evidence |
|---|---|
| No images were in the repository before this work. | `git ls-tree` on `release/v0.1.0-mvp` |
| PSI-69 (FLEX) holds about 860 GB of files, including a `Calibration` folder with per-test bundles for the first FLEX tests (20CAL08 … 40CAL01, PSI-69 table rows 1–9). | PSI-69 investigation page, "Data files and documents" |
| Each bundle has an event log, a per-camera frame index, camera settings, and image archives `A` (HIBMS backlit droplet, 30 fps), `B` and `D` (other cameras). | `PSI-69_Calibration_<T>*.txt`, `*.zip` |
| HIBMS: SMD 1M60-20 camera, 12-bit grey stored as 16-bit TIFF, 512 × 512 px, 30 fps. | `<T>_HIBMS_Camera_Settings.txt` |
| **No spatial calibration (mm/px) in any calibration file.** | camera, test-point and settings files read in full |
| Time calibration exists: per-frame timestamps (≈33 ms) and logged events (igniter-on, needle and igniter retraction). | `<T>A.txt`, `<T>.txt` |
| NASA's own files contain defects: 20CAL13 has no HIBMS archive and its readme lists missing frames, and `20CAL10A_01094.tif` is truncated. | readme; decoder error, frame flagged `unreadable_frame` |

Downloaded: 3 test bundles, about 1.0 GB in total (limit 2 GB). Every file is recorded with its URL, SHA-256, size, licence (CC0-1.0) and retrieval time in `data/metadata/vision_artifact_manifest.csv`. The raw files sit in the gitignored `data/raw/PSI-69/calibration/` and are read in place (zip members are decoded in memory and never extracted). The PSI investigation page, not this module, decides source eligibility, and the eligibility of PSI-69 (`PENDING_VERIFICATION`) is unchanged.

## 2. Feasibility: what can be measured

| Quantity | Status | Why |
|---|---|---|
| Droplet boundary, area, equivalent diameter (px) | **measured** | backlit droplet is a dark, round blob; sub-pixel accurate on synthetic disks |
| D²(t) slope K_px (px²/s) | **measured** | NASA timestamps give the time axis |
| Normalised rate K/D0² (1/s) | **measured, scale-free** | the pixel scale cancels, so it can be compared directly with NASA's reported K/D0² |
| Diameter, K or D_ext in mm | **not produced** | needs a documented mm/px scale; none is published in the calibration files |
| Visible-flame extinction diameter | **not measured** | the HIBMS backlit view does not show the flame; the droplet-side regime break is reported only as a proxy |
| Flame standoff, soot, temperature | out of scope | needs the flame cameras (B, D) and a radiometric or spectral method |

Calibration needed for mm values: a documented HIBMS magnification (mm/px) or a calibration-target image. Candidates are the FLEX Engineering Documents in PSI or Shaw (2014) on backlit-image interpretation. Until one is registered, results stay in pixels or are scale-free.

## 3. Pipeline (classical, no training)

`backend/app/vision/`:

| File | What it does |
|---|---|
| `nasa_bundle.py` | parses the event log, frame index and camera settings; decodes TIFF frames from the zip; returns `None` for corrupt frames |
| `segmentation.py` | dark mask at f × median background (f = 0.5, the half-intensity edge); external contours; rejects shapes that touch the border, are elongated (aspect > 1.3) or non-round (4πA/P² < 0.7); area = filled pixel count; nearest-to-track candidate |
| `metrology.py` | per-frame records; windows from NASA log events (below); OLS fit with a Student-t 95% CI; two-segment regime break; quality gates and abstention |
| `method_card.py` | method card (formula, assumptions, limits, abstention conditions) |
| `api.py` | read-only routes (section 6) |

`backend/scripts/run_flame_vision.py` (`fetch`, `run`) verifies SHA-256 against the manifest before reading anything and writes `data/derived/flame_vision/<T>/` and `evaluation.json`.

Windows are fixed **a priori from NASA's event log**, never tuned to match NASA's values:

- **t = 0:** `AS Burn to Completion/Igniter On`.
- **D0:** median diameter in [`AS Needles Retract` + 0.1 s, 0). The reported D0 is defined at igniter-on (NASA/TP-2015-216046 App. A.1).
- **Excluded:** [0, `AS Retract Completed` + 0.1 s], because the igniters are in the field of view.
- **Fit:** from the end of the exclusion to the D² regime break.

Quality gates (each makes the module abstain, not guess):

- tracking jump or diameter step > 25% between frames marks the frame unusable;
- fewer than 3 free-droplet frames before ignition;
- fit-window coverage < 80%;
- slope ≥ 0 or R² < 0.9.

## 4. Results (reproducible: `python backend/scripts/run_flame_vision.py run 20CAL10 20CAL12 30CAL06`)

| Test (PSI-69 run) | Fuel / end | Fit frames | R² | K/D0² vision (1/s) | K/D0² NASA (1/s) | Difference | Threshold sensitivity f = 0.4 / 0.5 / 0.6 |
|---|---|---|---|---|---|---|---|
| 20CAL10 (r002) | methanol / extinction | 136 | 0.995 | 0.1348 ± 0.7% (1σ) | 0.1734 | −22.3% | 0.1358 / 0.1348 / 0.1338 |
| 20CAL12 (r003) | methanol / extinction | 87 | 0.993 | 0.1907 | 0.2238 | −14.8% | 0.1932 / 0.1907 / 0.1907 |
| 30CAL06 (r008) | heptane / disruption | — | — | **abstained** | 0.0908 | — | — |

- **Segmentation:** on synthetic disks of 8–49 px, |error| ≤ 0.5 px (tests). The edge transition on NASA frames spans about 2 px, and the overlay images confirm the contour sits on the droplet edge.
- **Implied scale (consistency check only, never used):** NASA D0 / measured D0_px = 0.0571 and 0.0586 mm/px, which agree within 2.7%. That is inside NASA's stated ±50 µm droplet-size uncertainty and consistent with a fixed HIBMS magnification.
- **Physics visible in the data:** for methanol, K/D0² in the first half of the fit window exceeds the second half (20CAL10: 0.154 vs 0.118 1/s). This matches the known decrease of methanol burning rate as water is absorbed (Hicks et al., PSI-69 publications).
- **Heptane 30CAL06:** the tracked droplet is lost about 4 s after ignition; diameter steps exceed 25% and frames are flagged. A soot shell or debris obscures the droplet in backlit view. The module abstains and records the reason instead of reporting a near-zero rate.

## 5. Why this is "not validated"

The vision K/D0² is **systematically 15–22% below** NASA's reported value on both measurable tests. Segmentation threshold (< 1.5% effect) and fit noise (< 1%) do not explain the gap. The plausible causes are:

1. **Different windows.** NASA fits "from shortly after ignition to extinction"; our window starts about 1.4 s after igniter-on because the igniters hide the droplet. The early burning, which is the fastest for methanol, is therefore missing.
2. **Different end points.** NASA's window ends at visible-flame extinction, seen by the flame cameras; ours ends at the droplet-side regime break.
3. **NASA's D0 definition and uncertainty** (±50 µm, about ±2.7% in D0 and about ±5% in K/D0²).

Validation requires NASA's per-test fit windows, or the D²(t) histories in NASA/TP-2015-216046 Appendix B (that report is `UNREGISTERED`; registering it is a science-owner decision). It also needs more tests: 4 more bundles with HIBMS archives exist (20CAL08, 30CAL02, 30CAL03, 40CAL01).

## 6. Integration (read-only, no OpenCV or raw files needed by the API)

| Method and path | Returns |
|---|---|
| `GET /api/v1/vision/method` | `MethodCard` |
| `GET /api/v1/vision/evaluation` | cross-test table (`n_computable`, `n_abstained`, differences, implied-scale range, verdict) |
| `GET /api/v1/vision/tests/{test_point}` | full summary: results, NASA reference (with `run_id` = data-platform run, e.g. `PSI-69-r002`), comparison, provenance (file SHA-256s), or `computable: false` and `abstention_reason` |
| `GET /api/v1/vision/tests/{test_point}/series` | per-frame records in pixels, with status and flags for every frame (404 if abstained) |

`test_point` must match `^\d{2}CAL\d{2}$`, otherwise the API returns 422. Missing results return 404. The vision `run_id` links to `/api/v1/runs/{run_id}` on the data platform. No frontend change was made.

## 7. Run and test

```bash
pip install -e "backend[dev,vision]"                     # OpenCV only for processing
python backend/scripts/run_flame_vision.py fetch 20CAL10 20CAL12 30CAL06   # ~1 GB from PSI
python backend/scripts/run_flame_vision.py run   20CAL10 20CAL12 30CAL06
cd backend && pytest -q tests/vision_tests
```

The tests use synthetic **test-only** disks for segmentation accuracy, verbatim NASA file excerpts for parsing, synthetic D(t) series for the fit and abstention logic, and real-data checks (skipped without the raw archives): SHA-256 against the manifest, plus reproducibility of the stored result to 1e-12.

## 8. Remaining gaps

1. No mm/px calibration. This blocks all physical (mm) metrology.
2. Not validated against NASA K (section 5).
3. Sooting heptane flames are not measurable with the half-intensity method.
4. Flame (not droplet) metrology from the `B`/`D` cameras is not started.
5. The vision results are not yet stored in `analysis_results`. Their inputs are frames, not `measurements` rows, and storing them needs a data-platform decision on frame artifacts.
