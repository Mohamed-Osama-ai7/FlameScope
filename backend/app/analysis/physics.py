"""Physics-informed analyses of the PSI-69 FLEX run-level table (reported values only).

Only quantities that exist in the acquired PSI-69 table are used: initial droplet diameter D0, visible flame
extinction diameter Dext, the FLEX team's reported burning-rate constant K, burn time, ambient composition and
pressure. There is no D(t) series, so no new K is fitted here. Values, flags and usability come from the
verified loader (app.analysis.flex_run_level), the same one the Data Platform extractor uses.

1. d2_consistency  - internal consistency of (D0, Dext, K, burn time) with the d^2-law, D^2 = D0^2 - K t:
                     t_d2 = (D0^2 - Dext^2) / K ;  r = t_d2 / t_burn.
   A data-quality diagnostic, not a validation of the d^2-law: K is the FLEX team's linear fit of D^2(t)
   "from shortly after ignition to extinction" (NASA/TP-2015-216046 App. A.1), D0 is at igniter-on, and the
   definition of the tabulated burn time is not documented in this repository. r is therefore not expected
   to equal 1; runs far from their fuel's typical r are flagged for review, not corrected.
   Uncertainty: interval propagation of each value's reporting resolution (half a unit of the last decimal
   written in the source) and, optionally, a caller-supplied diameter bound; per-fuel median with a
   percentile bootstrap 95% CI (fixed seed).

2. oxygen_effect   - association between ambient O2 mole fraction and reported K within strata that hold
                     diluent (N2 only), pressure cluster and support mode fixed (the strata of analysis v0.2):
                     K = b0 + b1 X_O2 (+ b2 D0 as a sensitivity model), OLS with HC3 standard errors.
   Descriptive association only: runs were not randomised, other conditions vary, and support mode comes
   from the NASA/TP-2015-216046 captions (unregistered source; it is a stratifier, never evidence).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import statsmodels.api as sm
from scipy import stats

from app.analysis import flex_run_level as fx

ANALYSIS_VERSION = "physics-0.1.1"
PRESSURE = "ambient_pressure"
D0, DEXT, K, TB, O2 = (
    "initial_droplet_diameter",
    "extinction_diameter",
    "burning_rate_constant_mm2_s",
    "burn_time_s",
    "ambient_oxygen_mole_fraction",
)
# Flags that disqualify a value for these analyses (stricter than FlexRun.usable).
_BAD_FIELD_FLAGS = {"approximate", "zero_value_meaning_unconfirmed"}
_BAD_ROW_FLAGS = {"dext_exceeds_d0", "composition_sum_deviation"}
BOOTSTRAP_RESAMPLES = 9999
BOOTSTRAP_SEED = 20261114
MIN_N_SUMMARY = 5  # same floor as v0.2 rank correlations
MIN_N_REGRESSION = 8
MIN_DISTINCT_X = 3


def resolution_halfwidth(raw: str) -> float:
    """Half a unit of the last decimal written in the source text ('2.06' -> 0.005, '760' -> 0.5)."""
    s = raw.strip().lstrip("~")
    decimals = len(s.split(".", 1)[1]) if "." in s else 0
    return 0.5 * 10.0 ** (-decimals)


def _clean(r: fx.FlexRun, name: str) -> bool:
    return r.usable(name) and not (set(r.field_flags.get(name, [])) & _BAD_FIELD_FLAGS)


# ------------------------------------------------------------------ 1. d^2-law consistency


@dataclass(frozen=True)
class D2Row:
    run_id: str
    experiment_id: str
    fuel: str
    d0_mm: float
    dext_mm: float
    k_mm2_s: float
    burn_time_s: float
    t_d2_s: float
    ratio: float
    ratio_interval: tuple[float, float]
    review_flag: str | None = None


def d2_implied_duration(d0: float, dext: float, k: float) -> float:
    """t = (D0^2 - Dext^2) / K from D^2 = D0^2 - K t. Inputs must satisfy d0 > dext >= 0 and k > 0."""
    if not (d0 > dext >= 0 and k > 0):
        raise ValueError("requires D0 > Dext >= 0 and K > 0")
    return (d0 * d0 - dext * dext) / k


def ratio_interval(
    d0: float, dext: float, k: float, tb: float, h_d0: float, h_dext: float, h_k: float, h_tb: float
) -> tuple[float, float]:
    """Worst-case bounds of r = (D0^2 - Dext^2) / (K t_b) for each input within +/- its half-width.

    r increases with D0 and decreases with Dext, K and t_b, so the bounds are attained at the corners.
    The lower bound is clipped at 0 when the D0 and Dext intervals overlap.
    """
    num_lo = max(d0 - h_d0, 0.0) ** 2 - (dext + h_dext) ** 2
    num_hi = (d0 + h_d0) ** 2 - max(dext - h_dext, 0.0) ** 2
    den_lo, den_hi = (k - h_k) * (tb - h_tb), (k + h_k) * (tb + h_tb)
    lo = max(num_lo, 0.0) / den_hi
    hi = num_hi / den_lo if den_lo > 0 else math.inf
    return lo, hi


def _summary(vals: list[float]) -> dict[str, Any]:
    a = np.asarray(vals, float)
    q1, med, q3 = (float(x) for x in np.percentile(a, [25, 50, 75]))
    out: dict[str, Any] = {
        "n": int(a.size),
        "median": med,
        "q1": q1,
        "q3": q3,
        "min": float(a.min()),
        "max": float(a.max()),
    }
    if a.size >= MIN_N_SUMMARY:
        res = stats.bootstrap(
            (a,),
            np.median,
            n_resamples=BOOTSTRAP_RESAMPLES,
            method="percentile",
            confidence_level=0.95,
            rng=np.random.default_rng(BOOTSTRAP_SEED),
        )
        out["median_ci95"] = [float(res.confidence_interval.low), float(res.confidence_interval.high)]
    else:
        out["median_ci95"] = None
    return out


def d2_consistency(
    runs: list[fx.FlexRun], fuel: str | None = None, diameter_halfwidth_mm: float | None = None
) -> dict[str, Any]:
    excluded: Counter[str] = Counter()
    rows: list[D2Row] = []
    for r in runs:
        if fuel and r.fuel != fuel:
            continue
        if r.test_end != "Extinction":
            excluded[f"test_end:{r.test_end or 'blank'} (d^2 burn to extinction required)"] += 1
            continue
        bad = [n for n in (D0, DEXT, K, TB) if not _clean(r, n)]
        if bad:
            excluded["missing_or_flagged:" + ",".join(sorted(bad))] += 1
            continue
        if set(r.row_flags) & _BAD_ROW_FLAGS:
            excluded["row_flag:" + ",".join(sorted(set(r.row_flags) & _BAD_ROW_FLAGS))] += 1
            continue
        d0, dext, k, tb = (float(r.values[n]) for n in (D0, DEXT, K, TB))  # type: ignore[arg-type]
        if not (d0 > dext > 0 and k > 0 and tb > 0):
            excluded["non_physical_combination"] += 1
            continue
        hd = diameter_halfwidth_mm or 0.0
        h = {n: resolution_halfwidth(r.raw[n]) for n in (D0, DEXT, K, TB)}
        t = d2_implied_duration(d0, dext, k)
        rows.append(
            D2Row(
                run_id=f"PSI-69-r{r.psi_row:03d}",
                experiment_id=f"FLEX-{r.flex_test_number:03d}",
                fuel=r.fuel,
                d0_mm=d0,
                dext_mm=dext,
                k_mm2_s=k,
                burn_time_s=tb,
                t_d2_s=t,
                ratio=t / tb,
                ratio_interval=ratio_interval(d0, dext, k, tb, max(h[D0], hd), max(h[DEXT], hd), h[K], h[TB]),
            )
        )
    by_fuel: dict[str, Any] = {}
    flagged: list[D2Row] = []
    for f in sorted({x.fuel for x in rows}):
        fr = [x for x in rows if x.fuel == f]
        s = _summary([x.ratio for x in fr])
        iqr = s["q3"] - s["q1"]
        lo_f, hi_f = s["q1"] - 1.5 * iqr, s["q3"] + 1.5 * iqr
        s["tukey_fences"] = [lo_f, hi_f]
        s["share_of_intervals_containing_1"] = sum(
            x.ratio_interval[0] <= 1 <= x.ratio_interval[1] for x in fr
        ) / len(fr)
        by_fuel[f] = s
        for x in fr:
            if x.ratio < lo_f or x.ratio > hi_f:
                # flag only when the whole resolution interval lies outside the fences
                if x.ratio_interval[1] < lo_f or x.ratio_interval[0] > hi_f:
                    flagged.append(x)
    flagged_ids = {x.run_id for x in flagged}
    return {
        "analysis": "d2_consistency",
        "analysis_version": ANALYSIS_VERSION,
        "equation": "t_d2 = (D0^2 - Dext^2) / K ;  r = t_d2 / t_burn  (from D^2 = D0^2 - K t)",
        "value_origin": "reported_in_source (PSI-69); t_d2 and r are derived here",
        "n_runs": len(rows),
        "excluded": dict(excluded),
        "by_fuel": by_fuel,
        "flagged_for_review": [x.run_id for x in flagged],
        "runs": [
            {
                **x.__dict__,
                "ratio_interval": list(x.ratio_interval),
                "review_flag": "outside fuel Tukey fences beyond reporting resolution"
                if x.run_id in flagged_ids
                else None,
            }
            for x in rows
        ],
        "uncertainty": {
            "per_run": "worst-case interval from the reporting resolution of each value"
            + (f" and a diameter bound of +/-{diameter_halfwidth_mm} mm" if diameter_halfwidth_mm else ""),
            "summary": f"median with percentile bootstrap 95% CI ({BOOTSTRAP_RESAMPLES} resamples, "
            f"seed {BOOTSTRAP_SEED})",
        },
        "limitations": [
            "Diagnostic of internal consistency, not a validation of the d^2-law or of NASA values.",
            "K is the FLEX team's fit from shortly after ignition to extinction (excludes heat-up); D0 is "
            "at igniter-on; the definition of the tabulated burn time is not documented here, so r = 1 is "
            "not expected.",
            "Reported Dext may be extrapolated in some runs (noted in report captions, unregistered source).",
            "Flags mark runs for review; no value is corrected or removed from the source.",
        ],
    }


# ------------------------------------------------------------------ 2. O2 effect on reported K


def _ols(y: np.ndarray, x: np.ndarray, names: list[str]) -> dict[str, Any]:
    # HC3 robust covariance with Student-t inference on the residual dof (small strata)
    fit = sm.OLS(y, sm.add_constant(x, has_constant="add")).fit(cov_type="HC3", use_t=True)
    ci = fit.conf_int(alpha=0.05)
    return {
        name: {
            "estimate": float(fit.params[i]),
            "se_hc3": float(fit.bse[i]),
            "ci95": [float(ci[i][0]), float(ci[i][1])],
            "p_value": float(fit.pvalues[i]),
        }
        for i, name in enumerate(["intercept", *names])
    } | {"r_squared": float(fit.rsquared), "dof_resid": float(fit.df_resid)}


def oxygen_effect(runs: list[fx.FlexRun], fuel: str | None = None) -> dict[str, Any]:
    excluded: Counter[str] = Counter()
    kept: list[fx.FlexRun] = []
    for r in runs:
        if fuel and r.fuel != fuel:
            continue
        if r.diluent_family != "N2_only":
            excluded[
                f"diluent:{r.diluent_family} (O2 is the single compositional variable only with N2)"
            ] += 1
            continue
        bad = [n for n in (K, O2, D0, PRESSURE) if not _clean(r, n)]  # pressure defines the stratum
        if bad or set(r.row_flags) & _BAD_ROW_FLAGS:
            excluded["missing_or_flagged"] += 1
            continue
        kept.append(r)
    strata: list[dict[str, Any]] = []
    groups: dict[tuple[str, str | None, str], list[fx.FlexRun]] = {}
    for r in kept:
        groups.setdefault((r.fuel, r.pressure_cluster, r.support_mode), []).append(r)
    for (f, pc, smode), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        x = np.array([r.values[O2] for r in rows], float)
        y = np.array([r.values[K] for r in rows], float)
        d0 = np.array([r.values[D0] for r in rows], float)
        entry: dict[str, Any] = {
            "fuel": f,
            "pressure_cluster": pc,
            "support_mode": smode,
            "n": len(rows),
            "x_o2_range": [float(x.min()), float(x.max())],
            "n_distinct_o2": int(len(set(x.tolist()))),
            "run_ids": [f"PSI-69-r{r.psi_row:03d}" for r in rows],
        }
        if len(rows) < MIN_N_REGRESSION or entry["n_distinct_o2"] < MIN_DISTINCT_X:
            entry["computable"] = False
            entry["abstention_reason"] = (
                f"needs n >= {MIN_N_REGRESSION} and >= {MIN_DISTINCT_X} distinct O2 levels"
            )
        else:
            entry["computable"] = True
            entry["model_k_on_o2"] = _ols(y, x.reshape(-1, 1), ["x_o2"])
            entry["sensitivity_k_on_o2_and_d0"] = (
                _ols(y, np.column_stack([x, d0]), ["x_o2", "d0_mm"])
                if len(rows) >= MIN_N_REGRESSION + 2
                else None
            )
            entry["spearman_o2_k"] = fx.spearman(x.tolist(), y.tolist())
        strata.append(entry)
    return {
        "analysis": "oxygen_effect",
        "analysis_version": ANALYSIS_VERSION,
        "model": (
            "K = b0 + b1 * X_O2 ; sensitivity: K = b0 + b1 * X_O2 + b2 * D0 ; "
            "OLS, HC3 standard errors, Student-t 95% CI"
        ),
        "units": {"K": "mm^2/s", "X_O2": "mole fraction", "b1": "mm^2/s per unit mole fraction", "D0": "mm"},
        "value_origin": "reported K (FLEX team) and reported conditions (PSI-69); coefficients derived here",
        "strata_held_fixed": ["fuel", "diluent_family = N2_only", "pressure_cluster", "support_mode"],
        "excluded": dict(excluded),
        "strata": strata,
        "limitations": [
            "Association within strata, not a causal effect: runs were not randomised and D0 and other "
            "conditions vary (D0-adjusted model given as a sensitivity check).",
            "Support mode comes from NASA/TP-2015-216046 figure captions (unregistered source, pypdf text "
            "not visually verified); used only to avoid pooling support modes.",
            "Linear form is a local approximation over the observed O2 range; no extrapolation.",
            "Strata are small; HC3 intervals are wide and p-values are not corrected for multiple strata.",
        ],
    }
