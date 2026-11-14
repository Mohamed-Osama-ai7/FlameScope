"""Deterministic comparison gate (docs/03_scientific_gates.md).

Classifies a proposed comparison between two observations as one of:

* ``direct`` - same regime, material, apparatus, variable definition, unit and all recorded
  conditions.
* ``controlled_variation`` - as ``direct`` but exactly one recorded condition differs.
* ``contextual`` - informative but confounded (several differences, unknown conditions, or the
  same named quantity measured in different regimes).
* ``not_comparable`` - different variable definitions, incompatible dimensions, or a variable
  outside a regime's vocabulary. No shared quantitative axis may be drawn.

The gate never converts units: a same-dimension unit mismatch is reported as requiring an explicit,
documented conversion step and downgrades the result to ``contextual``.
"""
from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.regimes import (
    CROSS_CHECK_PAIRS,
    REGIME_VARIABLES,
    REQUIRED_CONDITIONS,
    VARIABLES,
    CombustionRegime,
    unit_dimension,
)


class ComparisonClass(str, Enum):
    DIRECT = "direct"
    CONTROLLED_VARIATION = "controlled_variation"
    CONTEXTUAL = "contextual"
    NOT_COMPARABLE = "not_comparable"


class Condition(BaseModel):
    value: float
    unit: str


class ObservationDescriptor(BaseModel):
    investigation_id: str = Field(min_length=1, examples=["PSI-69"])
    regime: CombustionRegime
    variable: str = Field(min_length=1, examples=["burning_rate_constant_mm2_s"])
    unit: str = Field(min_length=1, examples=["mm^2/s"])
    material_or_fuel: str | None = None
    apparatus: str | None = None
    conditions: dict[str, Condition] = Field(default_factory=dict)


class ComparisonRequest(BaseModel):
    a: ObservationDescriptor
    b: ObservationDescriptor


class ComparisonResult(BaseModel):
    classification: ComparisonClass
    shared_axis_allowed: bool
    reasons: list[str]
    held_constant: list[str]
    differing: list[str]
    unknown: list[str]


def _same(x: Condition, y: Condition) -> bool:
    return x.unit == y.unit and math.isclose(x.value, y.value, rel_tol=1e-9, abs_tol=0.0)


def _not_comparable(reasons: list[str]) -> ComparisonResult:
    return ComparisonResult(
        classification=ComparisonClass.NOT_COMPARABLE,
        shared_axis_allowed=False,
        reasons=reasons,
        held_constant=[],
        differing=[],
        unknown=[],
    )


def validate_comparison(a: ObservationDescriptor, b: ObservationDescriptor) -> ComparisonResult:
    reasons: list[str] = []

    for obs, label in ((a, "a"), (b, "b")):
        if obs.variable not in VARIABLES:
            reasons.append(f"{label}: variable '{obs.variable}' is not in the controlled vocabulary")
        elif obs.variable not in REGIME_VARIABLES[obs.regime]:
            reasons.append(
                f"{label}: variable '{obs.variable}' is not defined for regime '{obs.regime.value}'"
            )
        dim = unit_dimension(obs.unit)
        if dim is None:
            reasons.append(f"{label}: unit '{obs.unit}' is not registered")
        elif obs.variable in VARIABLES and VARIABLES[obs.variable].dimension != dim:
            reasons.append(
                f"{label}: unit '{obs.unit}' has dimension '{dim.value}', expected "
                f"'{VARIABLES[obs.variable].dimension.value}' for '{obs.variable}'"
            )
    if reasons:
        return _not_comparable(reasons)

    downgrade: list[str] = []
    if a.variable != b.variable:
        if frozenset({a.variable, b.variable}) not in CROSS_CHECK_PAIRS:
            return _not_comparable(
                [f"different variable definitions: '{a.variable}' vs '{b.variable}'"]
            )
        downgrade.append(
            "reported vs independently calculated burning-rate constant: cross-check only; "
            "fit windows and methods may differ, do not pool"
        )

    if a.unit != b.unit:
        downgrade.append(
            f"units differ ('{a.unit}' vs '{b.unit}'); an explicit, documented conversion is "
            "required before plotting on one axis"
        )

    if a.regime != b.regime:
        downgrade.append(
            f"different combustion regimes ('{a.regime.value}' vs '{b.regime.value}'); "
            "same named quantity but different scale, geometry and apparatus - no common "
            "response model is implied"
        )

    held: list[str] = []
    differing: list[str] = []
    unknown: list[str] = []

    for attr in ("material_or_fuel", "apparatus"):
        va, vb = getattr(a, attr), getattr(b, attr)
        if va is None or vb is None:
            unknown.append(attr)
        elif va.strip().lower() == vb.strip().lower():
            held.append(attr)
        else:
            differing.append(attr)

    required = REQUIRED_CONDITIONS[a.regime] | REQUIRED_CONDITIONS[b.regime]
    for key in sorted(set(a.conditions) | set(b.conditions) | required):
        ca, cb = a.conditions.get(key), b.conditions.get(key)
        if ca is None or cb is None:
            unknown.append(key)
        elif ca.unit != cb.unit:
            unknown.append(key)
            downgrade.append(f"condition '{key}' recorded in different units; not converted")
        elif _same(ca, cb):
            held.append(key)
        else:
            differing.append(key)

    if downgrade or unknown:
        classification = ComparisonClass.CONTEXTUAL
        if unknown:
            downgrade.append(
                "cannot establish that these are held constant: " + ", ".join(unknown)
            )
    elif not differing:
        classification = ComparisonClass.DIRECT
    elif len(differing) == 1 and differing[0] not in ("material_or_fuel", "apparatus"):
        classification = ComparisonClass.CONTROLLED_VARIATION
        downgrade.append(f"single isolated variable: {differing[0]}")
    else:
        classification = ComparisonClass.CONTEXTUAL
        downgrade.append("multiple uncontrolled differences: " + ", ".join(differing))

    return ComparisonResult(
        classification=classification,
        shared_axis_allowed=classification
        in (ComparisonClass.DIRECT, ComparisonClass.CONTROLLED_VARIATION),
        reasons=downgrade,
        held_constant=held,
        differing=differing,
        unknown=unknown,
    )
