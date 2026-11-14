"""Cross-check the vision K/D0^2 against the D^2(t) curves PUBLISHED in NASA/TP-2015-216046 (read-only).

The report prints, for every FLEX test, a figure of droplet diameter squared against time. This script
reads the red "Droplet history" markers of the figures of the three tests the vision module measured,
and compares the burning-rate slope of NASA's published curve with ours over the SAME physical window,
normalised by each curve's own pre-ignition plateau (so no spatial calibration is involved).

Status of the source: NASA/TP-2015-216046 is UNREGISTERED (data/metadata/source_eligibility.csv); its use
here is an exploratory cross-check, not evidence, until the science owner registers and approves it.

    FLAMESCOPE_NASA_TP_PDF=D:/FlameScope_raw/NASA-TP-2015-216046/20150023456.pdf \
        python backend/scripts/nasa_report_crosscheck.py

Output: data/derived/flame_vision/nasa_report_crosscheck.json. Needs the optional `pypdfium2` package.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.vision.metrology import fit_line, regime_break  # noqa: E402

ROOT = BACKEND.parent
OUT = ROOT / "data/derived/flame_vision/nasa_report_crosscheck.json"
PDF_ENV = "FLAMESCOPE_NASA_TP_PDF"
EXPECTED_SHA256 = "b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d"  # NTRS 20150023456
RENDER_SCALE = 4.0
# Axis calibrations read from the printed tick marks of each figure (render scale 4); +/-1 px = +/-0.5%.
# t = (x - x0) / px_per_s ;  D^2 = (y0 - y) / px_per_mm2 ; y_max = lowest pixel row of the plot area.
FIGURES: dict[str, dict[str, Any]] = {
    "20CAL10": dict(flex_test=2, figure=6, pdf_page=36, printed_page=30, x0=766.5, px_s=118.0, y0=1704.0,
                    px_mm2=210.5, y_max=1710, table_d0_mm=1.86, table_k_mm2_s=0.60),
    "20CAL12": dict(flex_test=3, figure=7, pdf_page=37, printed_page=31, x0=812.5, px_s=141.75, y0=1762.0,
                    px_mm2=299.0, y_max=1762, table_d0_mm=1.61, table_k_mm2_s=0.58),
    "30CAL03": dict(flex_test=5, figure=9, pdf_page=39, printed_page=33, x0=766.0, px_s=118.0, y0=1798.0,
                    px_mm2=225.0, y_max=1800, table_d0_mm=1.92, table_k_mm2_s=0.48),
}  # fmt: skip
CAL_TOLERANCE = 0.005  # +/-0.5% on each axis scale
ALIGN_TOLERANCE_S = 0.15  # +/-0.15 s on the kink alignment


def render(pdf_path: Path, page: int) -> Any:
    import pypdfium2 as pdfium

    bitmap = pdfium.PdfDocument(str(pdf_path))[page - 1].render(scale=RENDER_SCALE, rev_byteorder=True)
    return bitmap.to_numpy().astype(int)


def nasa_curve(image: Any, spec: dict[str, Any], px_s_scale: float = 1.0, px_mm2_scale: float = 1.0):
    """(t_s, d2_mm2) medians in 0.05 s bins of the red droplet-history markers."""
    import numpy as np

    red = (image[..., 0] > 170) & (image[..., 1] < 110) & (image[..., 2] < 110)
    ys, xs = np.nonzero(red[700 : spec["y_max"], 540:1990])
    ys, xs = ys + 700, xs + 540
    t = (xs - spec["x0"]) / (spec["px_s"] * px_s_scale)
    d2 = (spec["y0"] - ys) / (spec["px_mm2"] * px_mm2_scale)
    rows = []
    for a in np.arange(np.floor(t.min() * 20) / 20, t.max(), 0.05):
        m = (t >= a) & (t < a + 0.05)
        if m.sum() >= 6:
            rows.append((float(a + 0.025), float(np.median(d2[m]))))
    return rows


def plateau(curve: list[tuple[float, float]]) -> float:
    pre = sorted(y for t, y in curve if t < -0.7) or sorted(y for _, y in curve[:8])
    return pre[len(pre) // 2]


def window_slope(curve: list[tuple[float, float]], a: float, b: float) -> float:
    pts = [(t, y) for t, y in curve if a <= t <= b]
    return -fit_line([t for t, _ in pts], [y for _, y in pts]).slope


def decompose(
    table_d0_sq: float, plateau_mm2: float, table_k: float, curve_slope: float, ours: float, curve_norm: float
):
    """Multiplicative split of (ours / table-based NASA K/D0^2). The three factors multiply to the ratio."""
    f_d0 = (
        table_d0_sq / plateau_mm2
    )  # table normalises by the post-ignition D0, we by the pre-ignition plateau
    f_k = curve_slope / table_k  # NASA's published curve slope vs NASA's tabulated K (same window)
    f_meas = ours / curve_norm  # our measurement vs NASA's published curve
    return {"d0_definition": f_d0, "tabulated_k_vs_published_curve": f_k, "our_measurement_vs_curve": f_meas,
            "product": f_d0 * f_k * f_meas}  # fmt: skip


def analyse(test: str, spec: dict[str, Any], image: Any, summary: dict[str, Any]) -> dict[str, Any]:
    curve = nasa_curve(image, spec)
    pl = plateau(curve)
    t_k = regime_break(
        [t for t, _ in curve if t >= 0.5], [y for t, y in curve if t >= 0.5], 1.5, curve[-1][0] - 1.5
    )
    res = summary["results"]
    w0, w1 = res["windows_s"]["fit"]
    shift = (
        res["regime_break_t_s"] - t_k
    )  # our time axis minus NASA's, aligned on the burning->evaporation kink
    a, b = w0 - shift, w1 - shift
    slope = window_slope(curve, a, b)
    ours = res["k_over_d0sq_per_s"]
    rng = []
    for fs in (1 - CAL_TOLERANCE, 1 + CAL_TOLERANCE):
        for fm in (1 - CAL_TOLERANCE, 1 + CAL_TOLERANCE):
            c = nasa_curve(image, spec, fs, fm)
            for ds in (-ALIGN_TOLERANCE_S, 0.0, ALIGN_TOLERANCE_S):
                rng.append(window_slope(c, a + ds, b + ds) / plateau(c))
    d0_sq = spec["table_d0_mm"] ** 2
    at_zero = sorted(y for t, y in curve if -0.05 <= t <= 0.35)
    d2_zero = at_zero[len(at_zero) // 2]
    ref = summary["nasa_reference"]
    return {
        "flex_test": spec["flex_test"], "figure": spec["figure"], "pdf_page": spec["pdf_page"],
        "printed_page": spec["printed_page"], "run_id": ref["run_id"],
        "published_plateau_d2_mm2": pl, "published_plateau_d_mm": pl**0.5,
        "published_d_mm_at_plot_t0": d2_zero**0.5, "table_d0_mm": spec["table_d0_mm"],
        "published_kink_t_s": t_k, "our_kink_t_s": res["regime_break_t_s"], "time_axis_offset_s": shift,
        "our_window_s": [w0, w1], "published_axis_window_s": [a, b],
        "published_curve_slope_mm2_per_s": slope, "published_curve_k_over_plateau_per_s": slope / pl,
        "published_curve_k_over_plateau_range_per_s": [min(rng), max(rng)],
        "ours_k_over_d0sq_per_s": ours,
        "ours_vs_published_curve": ours / (slope / pl) - 1,
        "ours_vs_published_range": [ours / max(rng) - 1, ours / min(rng) - 1],
        "table_k_mm2_per_s": spec["table_k_mm2_s"],
        "table_k_over_d0sq_per_s": spec["table_k_mm2_s"] / d0_sq,
        "ours_vs_table_ratio": ours / (spec["table_k_mm2_s"] / d0_sq),
        "gap_decomposition": decompose(d0_sq, pl, spec["table_k_mm2_s"], slope, ours, slope / pl),
    }  # fmt: skip


def main() -> int:
    pdf = Path(os.environ.get(PDF_ENV) or ROOT / "data/raw/NASA-TP-2015-216046/20150023456.pdf")
    if not pdf.is_file():
        print(f"ERROR: report PDF not found: {pdf} (set {PDF_ENV})", file=sys.stderr)
        return 2
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if sha != EXPECTED_SHA256:
        print(f"ERROR: SHA-256 mismatch for {pdf}: {sha}", file=sys.stderr)
        return 2
    tests: dict[str, Any] = {}
    for test, spec in FIGURES.items():
        summary = json.loads((ROOT / f"data/derived/flame_vision/{test}/summary.json").read_text("utf-8"))
        tests[test] = analyse(test, spec, render(pdf, spec["pdf_page"]), summary)
    out = {
        "source": {"report": "NASA/TP-2015-216046", "ntrs_id": "20150023456", "sha256": sha,
                   "url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf",
                   "status": "UNREGISTERED (data/metadata/source_eligibility.csv); cross-check only"},
        "method": "red 'Droplet history' markers of the printed figures, 0.05 s median bins; axes calibrated "
                  "from tick marks; windows aligned on the burning->evaporation kink; "
                  "K divided by each curve's own plateau",
        "tolerances": {"axis_scale_rel": CAL_TOLERANCE, "kink_alignment_s": ALIGN_TOLERANCE_S},
        "tests": tests,
    }  # fmt: skip
    OUT.write_text(json.dumps(out, indent=2) + "\n", "utf-8")
    for t, r in tests.items():
        lo, hi = r["ours_vs_published_range"]
        print(f"OK   {t}: ours {r['ours_k_over_d0sq_per_s']:.4f} vs NASA published curve "
              f"{r['published_curve_k_over_plateau_per_s']:.4f} ({100 * r['ours_vs_published_curve']:+.1f}%, "
              f"range {100 * lo:+.1f}..{100 * hi:+.1f}%)")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
