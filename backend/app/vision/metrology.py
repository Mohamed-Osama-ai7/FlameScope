"""Droplet-diameter time series and scale-free d^2-law metrics from HIBMS frames.

Every window boundary comes from NASA's test-point event log, chosen a priori (never tuned to match
the reported values):

* t = 0 at ``AS Burn to Completion/Igniter On``;
* D0 = median diameter between ``AS Needles Retract`` + 0.1 s and t = 0 (free droplet before ignition;
  NASA/TP-2015-216046 Appendix A.1 defines the reported D0 at igniter-on);
* frames from t = 0 to ``AS Retract Completed`` + 0.1 s are excluded (igniters in the field of view);
* fit window starts at ``AS Retract Completed`` + 0.1 s and ends at the droplet-side regime break, the
  time that minimises a two-segment least-squares fit of D^2(t) (fast burning -> slow evaporation).

The HIBMS backlit view shows the droplet, not the flame, so the regime break is a droplet-side proxy
for extinction. It is reported, but it is not a measurement of the visible-flame extinction diameter.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any

from app.science.stats import student_t_ppf
from app.vision.nasa_bundle import HibmsBundle
from app.vision.segmentation import SegmentationParams, segment_droplet

METHOD_ID = "vision.hibms_droplet_d2_pixel"
METHOD_VERSION = "1.0.0"
EVENT_T0 = "AS Burn to Completion/Igniter On"
EVENT_NEEDLES_OUT = "AS Needles Retract"
EVENT_IGNITERS_OUT = "AS Retract Completed"
MARGIN_S = 0.1
MIN_FIT_POINTS = 10
MAX_JUMP_PX = 15.0  # allowed centroid jump between adjacent accepted frames
MAX_DRIFT_PX_PER_S = 30.0  # plus slow drift over longer gaps (excluded windows, unreadable frames)
MAX_REL_DIAMETER_STEP = 0.25  # |dD|/D between accepted frames; larger = lost droplet (soot shell, debris)
MIN_FIT_COVERAGE = 0.8  # usable frames / timestamped frames inside the fit window
MIN_FIT_R2 = 0.9
MAX_TAIL_SLOPE_RATIO = 0.3  # post-break D^2 slope / burning slope; larger = no burning->evaporation break
UNUSABLE_FLAGS = ("tracking_jump", "diameter_jump")
REANCHOR_FRAMES = 3  # consecutive mutually consistent detections that move a stale track anchor
SENSITIVITY_FRACTIONS = (0.4, 0.5, 0.6)


@dataclass
class FrameRecord:
    frame: str
    t_s: float | None
    status: str  # measured | no_droplet | unreadable_frame | no_timestamp | before_droplet_release
    #             | excluded_igniter_window
    diameter_px: float | None = None
    area_px: float | None = None
    circularity: float | None = None
    centroid_x_px: float | None = None
    centroid_y_px: float | None = None
    candidates: int | None = None
    flags: str = ""


@dataclass(frozen=True)
class LineFit:
    slope: float
    intercept: float
    slope_se: float
    slope_ci95: tuple[float, float]
    r_squared: float
    n: int
    t_start: float
    t_end: float


def fit_line(t: list[float], y: list[float]) -> LineFit:
    """Ordinary least squares with a Student-t 95% interval on the slope."""
    n = len(t)
    if n < 3:
        raise ValueError("at least 3 points are needed for a slope with uncertainty")
    tm, ym = sum(t) / n, sum(y) / n
    sxx = sum((a - tm) ** 2 for a in t)
    if sxx == 0:
        raise ValueError("time values are all equal")
    slope = sum((a - tm) * (b - ym) for a, b in zip(t, y, strict=True)) / sxx
    intercept = ym - slope * tm
    resid = [b - (intercept + slope * a) for a, b in zip(t, y, strict=True)]
    sse = sum(r * r for r in resid)
    sst = sum((b - ym) ** 2 for b in y)
    se = math.sqrt(sse / (n - 2) / sxx)
    q = student_t_ppf(0.975, n - 2)
    return LineFit(
        slope,
        intercept,
        se,
        (slope - q * se, slope + q * se),
        1 - sse / sst if sst else 0.0,
        n,
        min(t),
        max(t),
    )


def regime_break(t: list[float], y: list[float], t_lo: float, t_hi: float, step: float = 1 / 30) -> float:
    """Breakpoint minimising the summed squared error of two independent line fits."""
    best: tuple[float, float] | None = None
    tb = t_lo
    while tb <= t_hi:
        left = [(a, b) for a, b in zip(t, y, strict=True) if a <= tb]
        right = [(a, b) for a, b in zip(t, y, strict=True) if a > tb]
        if len(left) >= 5 and len(right) >= 5:
            sse = 0.0
            for part in (left, right):
                f = fit_line([a for a, _ in part], [b for _, b in part])
                sse += sum((b - (f.intercept + f.slope * a)) ** 2 for a, b in part)
            if best is None or sse < best[0]:
                best = (sse, tb)
        tb += step
    if best is None:
        raise ValueError("not enough points on both sides to locate a regime break")
    return best[1]


def measure_series(
    bundle: HibmsBundle, params: SegmentationParams, exclude_igniter_window: bool = True
) -> list[FrameRecord]:
    """Per-frame records. ``exclude_igniter_window=False`` is for the occlusion diagnostic only."""
    log = bundle.test_log()
    index = bundle.frame_index()
    t0 = log.event(EVENT_T0)
    release = (log.event(EVENT_NEEDLES_OUT) - t0).total_seconds() + MARGIN_S
    excl_end = (log.event(EVENT_IGNITERS_OUT) - t0).total_seconds() + MARGIN_S
    records: list[FrameRecord] = []
    last: FrameRecord | None = None
    pending: list[FrameRecord] = []  # position-only jumps that agree with each other (fast drift)
    for name in bundle.frame_names():
        stem = name.rsplit(".", 1)[0]
        stamp: datetime | None = index.get(stem)
        if stamp is None:
            records.append(FrameRecord(stem, None, "no_timestamp"))
            continue
        t = (stamp - t0).total_seconds()
        if t < release:  # droplet still on the dispensing needles: not a free droplet
            records.append(FrameRecord(stem, t, "before_droplet_release"))
            continue
        if exclude_igniter_window and 0.0 <= t <= excl_end:
            records.append(FrameRecord(stem, t, "excluded_igniter_window"))
            continue
        img = bundle.read_frame(name)
        if img is None:
            records.append(FrameRecord(stem, t, "unreadable_frame", flags="nasa_file_truncated_or_corrupt"))
            continue
        near = (last.centroid_x_px, last.centroid_y_px) if last and last.centroid_x_px is not None else None
        det = segment_droplet(img, params, near=near)  # type: ignore[arg-type]
        if det is None:
            records.append(FrameRecord(stem, t, "no_droplet"))
            continue
        flags = []
        if det.candidates > 1:
            flags.append("multiple_candidates")
        if last is not None and last.centroid_x_px is not None and last.centroid_y_px is not None:
            jump = math.hypot(det.centroid_x_px - last.centroid_x_px, det.centroid_y_px - last.centroid_y_px)
            gap = t - (last.t_s or t)
            if jump > MAX_JUMP_PX + MAX_DRIFT_PX_PER_S * max(gap, 0.0):
                flags.append("tracking_jump")
            if last.diameter_px and abs(det.equivalent_diameter_px - last.diameter_px) > (
                MAX_REL_DIAMETER_STEP * last.diameter_px
            ):
                flags.append("diameter_jump")
        rec = FrameRecord(
            stem,
            t,
            "measured",
            det.equivalent_diameter_px,
            det.area_px,
            det.circularity,
            det.centroid_x_px,
            det.centroid_y_px,
            det.candidates,
            ";".join(flags),
        )
        records.append(rec)
        if not any(f in flags for f in UNUSABLE_FLAGS):
            last = rec
            pending = []
        elif "diameter_jump" not in flags:
            # A drifting droplet can move further than the anchor allows across a long gap. Re-anchor
            # only on REANCHOR_FRAMES consecutive detections that agree in position with each other and
            # whose diameter already passed the step check; diameter jumps (debris, soot) never qualify.
            prev = pending[-1] if pending else None
            if (
                prev is not None
                and prev.t_s is not None
                and prev.centroid_x_px is not None
                and prev.centroid_y_px is not None
            ):
                step = math.hypot(
                    det.centroid_x_px - prev.centroid_x_px, det.centroid_y_px - prev.centroid_y_px
                )
                pending = (
                    pending + [rec] if step <= MAX_JUMP_PX + MAX_DRIFT_PX_PER_S * (t - prev.t_s) else [rec]
                )
            else:
                pending = [rec]
            if len(pending) >= REANCHOR_FRAMES:
                for p in pending:
                    p.flags = ";".join(
                        f if f != "tracking_jump" else "reanchored" for f in p.flags.split(";")
                    )
                last, pending = pending[-1], []
        else:
            pending = []
    return records


def _usable(r: FrameRecord) -> bool:
    return r.status == "measured" and not any(f in r.flags for f in UNUSABLE_FLAGS) and bool(r.diameter_px)


def analyse(records: list[FrameRecord], bundle: HibmsBundle) -> dict[str, Any]:
    """Scale-free d^2-law metrics. Raises ValueError (caller abstains) when a window is empty."""
    log = bundle.test_log()
    t0 = log.event(EVENT_T0)
    t_needles = (log.event(EVENT_NEEDLES_OUT) - t0).total_seconds() + MARGIN_S
    t_fit_start = (log.event(EVENT_IGNITERS_OUT) - t0).total_seconds() + MARGIN_S
    ok = [(r.t_s, r.diameter_px) for r in records if _usable(r) and r.t_s is not None and r.diameter_px]
    series: list[tuple[float, float]] = [
        (float(t), float(d)) for t, d in ok if t is not None and d is not None
    ]
    pre = sorted(d for t, d in series if t_needles <= t < 0.0)
    if len(pre) < 3:
        raise ValueError("fewer than 3 free-droplet frames between needle retraction and igniter-on")
    d0 = pre[len(pre) // 2] if len(pre) % 2 else 0.5 * (pre[len(pre) // 2 - 1] + pre[len(pre) // 2])
    d0_mad = sorted(abs(d - d0) for d in pre)[len(pre) // 2]
    burn = [(t, d**2) for t, d in series if t >= t_fit_start]
    if len(burn) < 2 * MIN_FIT_POINTS:
        raise ValueError("too few measured frames after the igniters left the field of view")
    tt = [a for a, _ in burn]
    yy = [b for _, b in burn]
    t_break = regime_break(tt, yy, t_fit_start + 1.0, max(tt) - 1.0)
    win = [(a, b) for a, b in burn if a <= t_break]
    tail = [(a, b) for a, b in burn if a > t_break]
    if len(win) < MIN_FIT_POINTS:
        raise ValueError("fit window has fewer than 10 frames")
    in_window = [r for r in records if r.t_s is not None and t_fit_start <= r.t_s <= t_break]
    coverage = len(win) / len(in_window) if in_window else 0.0
    if coverage < MIN_FIT_COVERAGE:
        raise ValueError(
            f"droplet tracked in only {coverage:.0%} of fit-window frames (< {MIN_FIT_COVERAGE:.0%}): "
            "droplet lost, obscured (e.g. soot shell) or touching the image edge; not measurable here"
        )
    fit = fit_line([a for a, _ in win], [b for _, b in win])
    tail_ratio = (
        fit_line([a for a, _ in tail], [b for _, b in tail]).slope / fit.slope if len(tail) >= 3 else None
    )
    if tail_ratio is None or tail_ratio > MAX_TAIL_SLOPE_RATIO:
        raise ValueError(
            "no burning-to-evaporation break in the droplet history (post-break/burning D^2 slope ratio "
            f"{'n/a' if tail_ratio is None else f'{tail_ratio:.2f}'} > {MAX_TAIL_SLOPE_RATIO}): "
            "e.g. disruption "
            "or droplet leaving the view before extinction, so the fit window end is undefined"
        )
    if fit.slope >= 0 or fit.r_squared < MIN_FIT_R2:
        raise ValueError(
            f"no d^2-law burning segment: slope {fit.slope:.1f} px^2/s, R^2 {fit.r_squared:.3f} "
            f"(requires slope < 0 and R^2 >= {MIN_FIT_R2})"
        )
    half = (win[0][0] + win[-1][0]) / 2
    first = fit_line([a for a, _ in win if a <= half], [b for a, b in win if a <= half])
    second = fit_line([a for a, _ in win if a > half], [b for a, b in win if a > half])
    k_px = -fit.slope
    k_norm = k_px / d0**2
    # relative uncertainty: slope standard error and D0 frame-to-frame dispersion (MAD, as 1-sigma proxy)
    rel = math.sqrt((fit.slope_se / k_px) ** 2 + (2 * 1.4826 * d0_mad / d0) ** 2)
    d_break = math.sqrt(max(fit.intercept + fit.slope * t_break, 0.0))
    return {
        "d0_px": d0,
        "d0_mad_px": d0_mad,
        "d0_frames": len(pre),
        "fit_window_coverage": coverage,
        "post_break_slope_ratio": tail_ratio,
        "fit": {**asdict(fit), "slope_px2_per_s": fit.slope},
        "k_px2_per_s": k_px,
        "k_over_d0sq_per_s": k_norm,
        "k_over_d0sq_rel_uncertainty_1sigma": rel,
        "k_over_d0sq_first_half_per_s": -first.slope / d0**2,
        "k_over_d0sq_second_half_per_s": -second.slope / d0**2,
        "regime_break_t_s": t_break,
        "regime_break_diameter_ratio": d_break / d0,
        "windows_s": {
            "d0": [t_needles, 0.0],
            "excluded_igniters": [0.0, t_fit_start],
            "fit": [t_fit_start, t_break],
        },
    }


def diagnostics(bundle: HibmsBundle, params: SegmentationParams, primary: dict[str, Any]) -> dict[str, Any]:
    """Evidence about the NASA gap. Diagnostic only: never changes the primary result or its windows.

    * occlusion: re-measures the igniter window (exclusion off) and reports which frames show a clean
      droplet and the longest interval with none (the physically hidden interval). Frames at the edges
      of that interval can be partly covered, so no rate is computed across it;
    * edge bias: the fit repeated with every diameter shifted by +/-0.5 px (the segmentation bias
      bound on synthetic disks) gives that term's effect on K/D0^2, separate from the fit error.
    """
    d0 = primary["d0_px"]
    t_start, t_break = primary["windows_s"]["fit"]
    recs = measure_series(bundle, params, exclude_igniter_window=False)
    clean = [
        (r.t_s, r.diameter_px)
        for r in recs
        if r.status == "measured" and not r.flags and r.t_s is not None and r.diameter_px and r.t_s > 0.0
    ]
    early = [(t, d) for t, d in clean if t < t_start]
    gap: dict[str, Any] = {"clean_frames_in_igniter_window": len(early)}
    seq = [(t, d) for t, d in clean if t <= t_start + 0.5]
    if len(seq) >= 2:
        (ta, da), (tb, db) = max(zip(seq, seq[1:], strict=False), key=lambda p: p[1][0] - p[0][0])
        gap.update(hidden_interval_s=[ta, tb], hidden_duration_s=tb - ta)
    burn = [
        (r.t_s, r.diameter_px)
        for r in recs
        if _usable(r) and r.t_s is not None and t_start <= r.t_s <= t_break
    ]
    edge = {}
    for shift in (-0.5, 0.5):
        f = fit_line([t for t, _ in burn], [(d + shift) ** 2 for _, d in burn])  # type: ignore[operator]
        edge[str(shift)] = -f.slope / (d0 + shift) ** 2
    bins = []
    t = t_start
    while t + 0.5 <= t_break:
        part = [(a, b * b) for a, b in burn if t <= a < t + 0.5]  # type: ignore[operator]
        if len(part) >= 5:
            bins.append(-fit_line([a for a, _ in part], [b for _, b in part]).slope / d0**2)
        t += 0.5
    return {
        "occlusion": gap,
        "edge_bias_k_over_d0sq": edge,
        "local_k_over_d0sq_0p5s_bins": bins,
        "max_local_k_over_d0sq_per_s": max(bins) if bins else None,
    }


def evaluate(bundle: HibmsBundle, params: SegmentationParams | None = None) -> dict[str, Any]:
    """Primary analysis at ``params`` plus threshold sensitivity; returns a JSON-ready summary."""
    base = params or SegmentationParams()
    records = measure_series(bundle, base)
    primary = analyse(records, bundle)
    primary["diagnostics"] = diagnostics(bundle, base, primary)
    sensitivity = {}
    for frac in SENSITIVITY_FRACTIONS:
        if abs(frac - base.threshold_fraction) < 1e-9:
            sensitivity[str(frac)] = primary["k_over_d0sq_per_s"]
            continue
        alt = analyse(measure_series(bundle, replace(base, threshold_fraction=frac)), bundle)
        sensitivity[str(frac)] = alt["k_over_d0sq_per_s"]
    counts: dict[str, int] = {}
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
    flagged = sum(1 for r in records if r.flags and r.status == "measured")
    return {
        "records": records,
        "summary": {
            **primary,
            "threshold_sensitivity_k_over_d0sq": sensitivity,
            "frame_status_counts": dict(sorted(counts.items())),
            "measured_frames_with_flags": flagged,
            "segmentation_params": asdict(base),
        },
    }
