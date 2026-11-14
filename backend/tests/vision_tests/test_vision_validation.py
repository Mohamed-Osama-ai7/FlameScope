"""Regression tests for the NASA-gap investigation helpers (pre-declared rules, raw-data location)."""

from __future__ import annotations

import pytest

from app.vision.nasa_bundle import RAW_DIR_ENV, raw_dir
from app.vision.validation import occlusion_verdict, uncertainty_budget


def summary(k=0.1348, fit=(1.53, 6.23), fastest=0.169, hidden=0.6):
    """Shape of metrology.evaluate()['summary'] restricted to the fields the helpers read."""
    return {
        "k_over_d0sq_per_s": k,
        "windows_s": {"fit": list(fit)},
        "diagnostics": {
            "max_local_k_over_d0sq_per_s": fastest,
            "occlusion": {"hidden_duration_s": hidden},
            "edge_bias_k_over_d0sq": {"-0.5": k * 0.993, "0.5": k * 1.007},
        },
        "fit": {"slope": -143.2, "slope_se": 0.875},
        "d0_px": 32.6,
        "d0_mad_px": 0.03,
        "k_over_d0sq_rel_uncertainty_1sigma": 0.0067,
        "threshold_sensitivity_k_over_d0sq": {"0.4": k * 1.008, "0.5": k, "0.6": k * 0.992},
    }


def test_required_rate_rejects_occlusion_for_20cal10_numbers():
    v = occlusion_verdict(summary(), nasa=0.1734, burn_time=5.0)
    assert v["verdict"] == "rejected_as_main_cause"
    assert v["implied_ignition_t_s"] == pytest.approx(1.23)
    assert v["hidden_part_of_nasa_window_s"] == pytest.approx(0.30)
    assert v["required_hidden_k_over_d0sq_per_s"] > 2 * v["fastest_observed_local_k_over_d0sq_per_s"]


def test_required_rate_marks_plausible_when_hidden_rate_is_reachable():
    # long hidden part and small gap: the needed rate is below the fastest observed rate
    v = occlusion_verdict(summary(k=0.160, fit=(2.0, 6.0), fastest=0.25), nasa=0.170, burn_time=5.0)
    assert v["verdict"] == "plausible" and v["required_hidden_k_over_d0sq_per_s"] <= 0.25


def test_no_hidden_part_means_rejected_and_bad_assumption_means_uncertain():
    assert occlusion_verdict(summary(fit=(1.0, 6.0)), nasa=0.17, burn_time=4.0)["verdict"] == (
        "rejected_as_main_cause"
    )
    assert occlusion_verdict(summary(fit=(1.5, 3.0)), nasa=0.17, burn_time=5.0)["verdict"] == "uncertain"
    assert occlusion_verdict(summary(), nasa=None, burn_time=5.0)["verdict"] == "uncertain"


def test_uncertainty_budget_keeps_terms_separate():
    b = uncertainty_budget(summary())
    assert b["fit_slope_rel_1sigma"] == pytest.approx(0.875 / 143.2)
    assert b["edge_bias_0p5px_rel_range"] == pytest.approx([-0.007, 0.007])
    assert b["threshold_sensitivity_rel_range"] == pytest.approx([-0.008, 0.008])
    assert "not the total" in b["note"] and "window" in b["not_quantified"]


def test_raw_dir_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv(RAW_DIR_ENV, str(tmp_path))
    assert raw_dir() == tmp_path
    monkeypatch.delenv(RAW_DIR_ENV)
    assert raw_dir().parts[-3:] == ("raw", "PSI-69", "calibration")


# ------------------------------------------------------------ NASA report cross-check (docs/16 section 5)


def test_gap_decomposition_factors_multiply_to_the_ratio():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "crosscheck", Path(__file__).resolve().parents[2] / "scripts" / "nasa_report_crosscheck.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # numbers shaped like 20CAL10: table D0 1.86 mm, plateau 4.01 mm2, K 0.60, curve slope 0.546 mm2/s
    d = mod.decompose(1.86**2, 4.01, 0.60, 0.546, ours=0.1348, curve_norm=0.546 / 4.01)
    ratio = 0.1348 / (0.60 / 1.86**2)
    assert d["product"] == pytest.approx(ratio)
    assert d["d0_definition"] < 1 and d["tabulated_k_vs_published_curve"] < 1
    assert d["our_measurement_vs_curve"] == pytest.approx(0.1348 / (0.546 / 4.01))
