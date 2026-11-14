"""d^2-law tests on analytic series (synthetic test inputs, never presented as NASA data)."""
import math

import pytest

from app.science.droplet import DropletSeries, Provenance, fit_burning_rate_constant
from app.science.method_cards import D2_LAW_CARD

PROV = Provenance(
    source_id="TEST-ANALYTIC",
    source_locator="generated in test",
    extraction_method="analytic",
)


BASE = dict(
    run_id="test",
    regime="flex_droplet",
    fuel="test-fuel",
    time_unit="s",
    diameter_unit="mm",
    window_selection="whole analytic series",
)


def series(t, d, sigma=None):
    return DropletSeries.model_validate(
        {**BASE, "time_s": t, "diameter_mm": d, "diameter_sigma_mm": sigma, "provenance": PROV}
    )


def analytic(d0=3.0, k=0.6, n=20, t_end=10.0):
    t = [i * t_end / (n - 1) for i in range(n)]
    d = [math.sqrt(d0**2 - k * ti) for ti in t]
    return t, d


def test_recovers_exact_k_and_intercept():
    t, d = analytic()
    r = fit_burning_rate_constant(series(t, d))
    assert r.computable
    assert r.k_mm2_per_s == pytest.approx(0.6, rel=1e-9)
    assert r.d0_squared_mm2 == pytest.approx(9.0, rel=1e-9)
    assert r.r_squared == pytest.approx(1.0)


def test_weighted_fit_reports_uncertainty_and_ci_contains_k():
    t, d = analytic()
    r = fit_burning_rate_constant(series(t, d, sigma=[0.01] * len(t)))
    assert r.weighted
    assert r.k_std_error_mm2_per_s > 0
    lo, hi = r.k_ci95_mm2_per_s
    assert lo < 0.6 < hi


def test_noisy_fit_ci_covers_truth():
    t, d = analytic()
    noise = [0.002 * ((-1) ** i) for i in range(len(d))]
    r = fit_burning_rate_constant(series(t, [di + e for di, e in zip(d, noise, strict=True)]))
    lo, hi = r.k_ci95_mm2_per_s
    assert lo < 0.6 < hi


@pytest.mark.parametrize(
    "t,d,reason",
    [
        ([0, 1], [2.0, 1.9], "at least 3"),
        ([0, 1, 1], [2.0, 1.9, 1.8], "strictly increasing"),
        ([0, 1, 2], [2.0, 0.0, 1.8], "positive"),
        ([0, 1, 2], [1.8, 1.9, 2.0], "not decreasing"),
    ],
)
def test_abstains_instead_of_guessing(t, d, reason):
    r = fit_burning_rate_constant(series(t, d))
    assert not r.computable
    assert r.k_mm2_per_s is None
    assert reason in r.abstention_reason


def test_provenance_is_required():
    with pytest.raises(ValueError):
        DropletSeries.model_validate({**BASE, "time_s": [0, 1, 2], "diameter_mm": [2, 1.9, 1.8]})


@pytest.mark.parametrize(
    "override",
    [
        {"regime": "bass_ii_solid"},
        {"regime": "saffire_spacecraft_scale"},
        {"time_unit": "ms"},
        {"diameter_unit": "m"},
        {"window_selection": ""},
        {"fuel": ""},
    ],
)
def test_out_of_scope_regime_or_units_rejected(override):
    t, d = analytic()
    with pytest.raises(ValueError):
        DropletSeries.model_validate(
            {**BASE, **override, "time_s": t, "diameter_mm": d, "provenance": PROV}
        )


def test_result_exposes_assumptions_limits_and_unvalidated_status():
    t, d = analytic()
    r = fit_burning_rate_constant(series(t, d))
    assert r.assumptions and r.validity_limits
    assert r.validation_status == "implemented_unvalidated_on_nasa_data"
    assert any("no diameter uncertainty" in w for w in r.warnings)


def test_nonlinear_d2_history_is_flagged():
    t = [float(i) for i in range(20)]
    d = [math.sqrt(max(9.0 - 0.02 * ti**2, 0.05)) for ti in t]  # curved D^2(t)
    r = fit_burning_rate_constant(series(t, d))
    assert any("non-linear" in w for w in r.warnings)


def test_method_card_is_complete():
    assert D2_LAW_CARD.references and D2_LAW_CARD.validity_limits and D2_LAW_CARD.assumptions
    assert {v.unit for v in D2_LAW_CARD.variables if v.role == "output"} >= {"mm^2/s"}
    assert all(ref.doi for ref in D2_LAW_CARD.references)  # each DOI verified via Crossref
