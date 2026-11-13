"""Small, dependency-free statistics helpers.

Student-t quantile via the regularized incomplete beta function, evaluated with the modified
Lentz continued fraction (Press et al., Numerical Recipes, 3rd ed., sec. 6.4), and inverted by
bisection. Accuracy is checked in tests against standard t-table values. Replace with
``scipy.stats.t.ppf`` once SciPy is part of the installed stack.
"""
from __future__ import annotations

import math

_EPS = 1e-15
_TINY = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            return h
    raise ArithmeticError("incomplete beta continued fraction did not converge")


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if not 0.0 <= x <= 1.0:
        raise ValueError("x must be in [0, 1]")
    if x in (0.0, 1.0):
        return x
    log_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, dof: float) -> float:
    if dof <= 0:
        raise ValueError("degrees of freedom must be positive")
    tail = 0.5 * regularized_incomplete_beta(dof / 2.0, 0.5, dof / (dof + t * t))
    return 1.0 - tail if t >= 0 else tail


def student_t_ppf(p: float, dof: float) -> float:
    """Inverse CDF of Student's t for 0 < p < 1 (bisection to ~1e-12 relative)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -student_t_ppf(1.0 - p, dof)
    lo, hi = 0.0, 1.0
    while student_t_cdf(hi, dof) < p:
        hi *= 2.0
        if hi > 1e12:
            raise ArithmeticError("quantile bracket overflow")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, dof) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-12 * max(1.0, hi):
            break
    return 0.5 * (lo + hi)
