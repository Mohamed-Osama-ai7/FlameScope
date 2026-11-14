"""Pure validation helpers for the flame-vision NASA comparison (docs/16 section 9).

Both functions only read a ``results`` summary from ``metrology.evaluate`` plus NASA-reported values;
they never change a measurement.
"""

from __future__ import annotations

from typing import Any


def occlusion_verdict(s: dict[str, Any], nasa: float | None, burn_time: float | None) -> dict[str, Any]:
    """Pre-declared required-rate test (docs/16 section 9), applied unchanged to every test.

    Assumption (stated, not verified): the droplet regime break is flame extinction, so NASA's window
    is about [t_break - burn_time, t_break]. H = part of that window before our fit start (hidden).
    R = average K/D0^2 the hidden part would need for the full-window average to equal NASA's value.
    rejected_as_main_cause: H <= 0, or R > 2 x the fastest observed local rate.
    plausible: R <= the fastest observed local rate. Otherwise: uncertain.
    """
    ours: float = s["k_over_d0sq_per_s"]
    t0, t1 = (float(x) for x in s["windows_s"]["fit"])
    fastest = s["diagnostics"]["max_local_k_over_d0sq_per_s"]
    base = {"assumption": "droplet regime break = flame extinction",
            "physically_hidden_s": s["diagnostics"]["occlusion"].get("hidden_duration_s")}  # fmt: skip
    if not nasa or not burn_time or not fastest:
        return {**base, "verdict": "uncertain", "reason": "missing NASA K/D0^2, burn time or local rates"}
    t_ign = t1 - burn_time
    hidden = max(0.0, t0 - max(t_ign, 0.0))
    seen = t1 - t0
    required = (nasa * (seen + hidden) - ours * seen) / hidden if hidden > 0 else None
    if t_ign < 0:
        verdict = "uncertain"  # implied ignition before igniter-on: the assumption fails for this test
    elif hidden <= 0 or (required is not None and required > 2 * fastest):
        verdict = "rejected_as_main_cause"
    elif required is not None and required <= fastest:
        verdict = "plausible"
    else:
        verdict = "uncertain"
    return {**base, "verdict": verdict, "implied_ignition_t_s": t_ign, "hidden_part_of_nasa_window_s": hidden,
            "required_hidden_k_over_d0sq_per_s": required,
            "fastest_observed_local_k_over_d0sq_per_s": fastest}  # fmt: skip


def uncertainty_budget(s: dict[str, Any]) -> dict[str, Any]:
    """Separate terms (relative to K/D0^2). Not summed: the systematic window term is not quantified."""
    k = s["k_over_d0sq_per_s"]
    fit = s["fit"]
    thr = list(s["threshold_sensitivity_k_over_d0sq"].values())
    edge = list(s["diagnostics"]["edge_bias_k_over_d0sq"].values())
    return {
        "fit_slope_rel_1sigma": fit["slope_se"] / abs(fit["slope"]),
        "d0_dispersion_rel_1sigma": 2 * 1.4826 * s["d0_mad_px"] / s["d0_px"],
        "combined_random_rel_1sigma": s["k_over_d0sq_rel_uncertainty_1sigma"],
        "threshold_sensitivity_rel_range": [min(thr) / k - 1, max(thr) / k - 1],
        "edge_bias_0p5px_rel_range": [min(edge) / k - 1, max(edge) / k - 1],
        "not_quantified": "fit-window definition (start hidden by igniters, end = droplet-side regime break, "
        "not flame extinction) and the definition of NASA's reported D0 and K",
        "note": "+/-0.5 px is the segmentation bias bound on synthetic disks (an edge term), not the "
        "total measurement uncertainty.",
    }
