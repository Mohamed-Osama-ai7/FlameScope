"""d^2-law burning-rate constant (see METHOD card droplet.d2_law_burning_rate_constant).

Scope guard: accepts only isolated liquid-fuel droplet series (regime ``flex_droplet``) with time in
seconds and diameter in millimetres. Other regimes or units are rejected at validation (HTTP 422);
units are never converted implicitly.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, model_validator

from app.domain.regimes import CombustionRegime
from app.science.method_cards import D2_LAW_CARD
from app.science.stats import student_t_ppf

# Heuristic diagnostics only; not acceptance criteria. Reported as warnings, never used to accept.
_FEW_POINTS = 10
_LINEARITY_R2 = 0.98


class Provenance(BaseModel):
    source_id: str = Field(min_length=1, examples=["PSI-69"])
    source_locator: str = Field(
        min_length=1, description="File + page/table/frame range the series was extracted from"
    )
    artifact_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    extraction_method: str = Field(min_length=1)


class DropletSeries(BaseModel):
    run_id: str = Field(min_length=1)
    regime: Literal[CombustionRegime.FLEX_DROPLET] = Field(
        description="Only isolated liquid-fuel droplet combustion is in scope for the d^2-law."
    )
    fuel: str = Field(min_length=1, description="Liquid fuel as named in the source.")
    time_unit: Literal["s"]
    diameter_unit: Literal["mm"]
    window_selection: str = Field(
        min_length=1,
        description=(
            "How the quasi-steady window was chosen (e.g. 'frames 120-480: after ignition "
            "transient, before extinction, per source fig. 3'). The tool does not choose it."
        ),
    )
    time_s: list[float] = Field(min_length=1)
    diameter_mm: list[float] = Field(min_length=1)
    diameter_sigma_mm: list[float] | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def _lengths(self) -> DropletSeries:
        n = len(self.time_s)
        if len(self.diameter_mm) != n:
            raise ValueError("time_s and diameter_mm must have the same length")
        if self.diameter_sigma_mm is not None and len(self.diameter_sigma_mm) != n:
            raise ValueError("diameter_sigma_mm must match time_s length")
        return self


class BurningRateResult(BaseModel):
    output_variable: Literal["burning_rate_constant_d2_fit_mm2_s"] = "burning_rate_constant_d2_fit_mm2_s"
    value_origin: Literal["calculated_from_diameter_history"] = "calculated_from_diameter_history"
    method_id: str
    method_version: str
    computable: bool
    abstention_reason: str | None = None
    run_id: str
    fuel: str
    n_points: int
    k_mm2_per_s: float | None = None
    k_std_error_mm2_per_s: float | None = None
    k_ci95_mm2_per_s: tuple[float, float] | None = None
    d0_squared_mm2: float | None = None
    r_squared: float | None = None
    weighted: bool = False
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str]
    validity_limits: list[str]
    uncertainty_note: str
    window_selection: str
    validation_status: str
    provenance: Provenance


def _base(series: DropletSeries) -> dict[str, object]:
    return {
        "method_id": D2_LAW_CARD.method_id,
        "method_version": D2_LAW_CARD.version,
        "run_id": series.run_id,
        "fuel": series.fuel,
        "n_points": len(series.time_s),
        "assumptions": D2_LAW_CARD.assumptions,
        "validity_limits": D2_LAW_CARD.validity_limits,
        "uncertainty_note": D2_LAW_CARD.uncertainty_method,
        "window_selection": series.window_selection,
        "validation_status": D2_LAW_CARD.status,
        "provenance": series.provenance,
    }


def _abstain(series: DropletSeries, reason: str) -> BurningRateResult:
    return BurningRateResult.model_validate(
        {**_base(series), "computable": False, "abstention_reason": reason}
    )


def fit_burning_rate_constant(series: DropletSeries) -> BurningRateResult:
    t = np.asarray(series.time_s, dtype=float)
    d = np.asarray(series.diameter_mm, dtype=float)
    n = t.size

    if n < 3:
        return _abstain(series, "at least 3 samples are required for a slope with uncertainty")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(d)):
        return _abstain(series, "non-finite time or diameter values")
    if np.any(np.diff(t) <= 0):
        return _abstain(series, "time must be strictly increasing")
    if np.any(d <= 0):
        return _abstain(series, "diameters must be positive")

    y = d**2
    design = np.column_stack([np.ones(n), t])
    weighted = series.diameter_sigma_mm is not None
    dof = n - 2

    if weighted:
        sigma_d = np.asarray(series.diameter_sigma_mm, dtype=float)
        if np.any(~np.isfinite(sigma_d)) or np.any(sigma_d <= 0):
            return _abstain(series, "diameter uncertainties must be positive and finite")
        sigma_y = 2.0 * d * sigma_d
        w = 1.0 / sigma_y**2
        normal = design.T @ (design * w[:, None])
        beta = np.linalg.solve(normal, design.T @ (w * y))
        cov = np.linalg.inv(normal)  # absolute sigmas: covariance not rescaled
    else:
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        resid = y - design @ beta
        cov = (float(resid @ resid) / dof) * np.linalg.inv(design.T @ design)

    intercept, slope = float(beta[0]), float(beta[1])
    k = -slope
    if k <= 0:
        return _abstain(series, "fitted K <= 0: D^2 is not decreasing over the window")

    se = float(np.sqrt(cov[1, 1]))
    tcrit = student_t_ppf(0.975, dof)
    fitted = design @ beta
    ss_res = float(np.sum((y - fitted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    warnings: list[str] = []
    if n < _FEW_POINTS:
        warnings.append(f"only {n} samples; uncertainty estimate is weak (heuristic threshold)")
    if r2 < _LINEARITY_R2:
        warnings.append(
            f"R^2={r2:.3f} < {_LINEARITY_R2} (heuristic): D^2(t) may be non-linear "
            "(transient, cool-flame or near-extinction data in window); a single K may be invalid"
        )
    if not weighted:
        warnings.append("no diameter uncertainty supplied; CI reflects scatter only")

    return BurningRateResult.model_validate(
        {
            **_base(series),
            "computable": True,
            "k_mm2_per_s": k,
            "k_std_error_mm2_per_s": se,
            "k_ci95_mm2_per_s": (k - tcrit * se, k + tcrit * se),
            "d0_squared_mm2": intercept,
            "r_squared": r2,
            "weighted": weighted,
            "warnings": warnings,
        }
    )
