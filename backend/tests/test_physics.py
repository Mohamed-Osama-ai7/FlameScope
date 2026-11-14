"""Physics-informed analyses: analytic examples, synthetic recovery, real PSI-69 regression, API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analysis import physics as p
from app.analysis.flex_run_level import FlexRun
from app.main import app

NAMES = (p.D0, p.DEXT, p.K, p.TB, p.O2, p.PRESSURE)


def run(
    i: int,
    d0="2.00",
    dext="1.00",
    k="0.50",
    tb="6.0",
    o2="0.21",
    *,
    fuel="Heptane",
    end="Extinction",
    pc="~1 atm",
    smode="free_floating",
    fam="N2_only",
    field_flags=None,
    row_flags=None,
) -> FlexRun:
    raw = dict(zip(NAMES, (d0, dext, k, tb, o2, "760"), strict=True))
    values = {n: (float(v.lstrip("~")) if v else None) for n, v in raw.items()}
    flags = {n: ([] if v else ["missing_blank"]) for n, v in raw.items()}
    for n, f in (field_flags or {}).items():
        flags[n].append(f)
    return FlexRun(
        psi_row=i,
        identifier=f"X{i}",
        test_date="1/1/2010",
        test_time_gmt="0:00:00",
        fuel=fuel,
        test_end=end,
        raw=raw,
        values=values,
        field_flags=flags,
        row_flags=list(row_flags or []),
        diluent_family=fam,
        pressure_cluster=pc,
        flex_test_number=i,
        support_mode=smode,
    )


# ------------------------------------------------------------------ equations


def test_resolution_halfwidth_follows_the_written_decimals():
    assert p.resolution_halfwidth("2.06") == pytest.approx(0.005)
    assert p.resolution_halfwidth("760") == pytest.approx(0.5)
    assert p.resolution_halfwidth("18.9") == pytest.approx(0.05)
    assert p.resolution_halfwidth("~6") == pytest.approx(0.5)


def test_d2_implied_duration_analytic():
    # D^2 = D0^2 - K t: from 2 mm to 1 mm at K = 0.5 mm^2/s takes (4 - 1) / 0.5 = 6 s
    assert p.d2_implied_duration(2.0, 1.0, 0.5) == pytest.approx(6.0)
    with pytest.raises(ValueError):
        p.d2_implied_duration(1.0, 1.0, 0.5)
    with pytest.raises(ValueError):
        p.d2_implied_duration(2.0, 1.0, 0.0)


def test_ratio_interval_corners_by_hand():
    assert p.ratio_interval(2, 1, 0.5, 6, 0, 0, 0, 0) == pytest.approx((1.0, 1.0))
    lo, hi = p.ratio_interval(2, 1, 0.5, 6, 0.005, 0.005, 0.005, 0.05)
    # lo = (1.995^2 - 1.005^2) / (0.505 * 6.05) ; hi = (2.005^2 - 0.995^2) / (0.495 * 5.95)
    assert lo == pytest.approx(2.97 / 3.05525)
    assert hi == pytest.approx(3.03 / 2.94525)


# ------------------------------------------------------------------ d^2 consistency on synthetic runs


def test_d2_consistency_excludes_and_summarises_deterministically():
    runs = [run(i, tb=f"{6.0 + 0.1 * (i % 5):.1f}") for i in range(1, 11)]
    runs += [
        run(20, end="Disruption"),
        run(21, dext=""),  # missing extinction diameter
        run(22, tb="~6", field_flags={p.TB: "approximate"}),
        run(23, row_flags=["dext_exceeds_d0"]),
        run(24, dext="0", field_flags={p.DEXT: "zero_value_meaning_unconfirmed"}),
        run(25, tb="2.0"),  # r = 3: far outside the fences
    ]
    a = p.d2_consistency(runs)
    b = p.d2_consistency(runs)
    assert a == b  # bootstrap seed fixed
    assert a["n_runs"] == 11
    assert sum(a["excluded"].values()) == 5
    s = a["by_fuel"]["Heptane"]
    assert s["median_ci95"][0] <= s["median"] <= s["median_ci95"][1]
    assert a["flagged_for_review"] == ["PSI-69-r025"]
    r1 = next(x for x in a["runs"] if x["run_id"] == "PSI-69-r001")
    assert r1["t_d2_s"] == pytest.approx(6.0) and r1["ratio"] == pytest.approx(6.0 / 6.1)


def test_diameter_bound_widens_intervals():
    runs = [run(i) for i in range(1, 6)]
    narrow = p.d2_consistency(runs)["runs"][0]["ratio_interval"]
    wide = p.d2_consistency(runs, diameter_halfwidth_mm=0.05)["runs"][0]["ratio_interval"]
    assert wide[0] < narrow[0] and wide[1] > narrow[1]


# ------------------------------------------------------------------ O2 effect on synthetic runs


def test_oxygen_effect_recovers_an_exact_line_and_abstains_on_small_strata():
    # K = 0.2 + 2.0 * X_O2 exactly, 8 runs over 4 O2 levels
    o2s = [0.15, 0.15, 0.21, 0.21, 0.25, 0.25, 0.30, 0.30]
    runs = [
        run(i, k=f"{0.2 + 2.0 * x:.2f}", o2=f"{x:.2f}", d0=f"{2.0 + 0.1 * i:.1f}")
        for i, x in enumerate(o2s, 1)
    ]
    runs += [run(50 + i, o2="0.21", pc="~0.7 atm") for i in range(3)]  # small stratum
    runs += [run(60, fam="CO2_added")]
    out = p.oxygen_effect(runs)
    big = next(s for s in out["strata"] if s["pressure_cluster"] == "~1 atm")
    m = big["model_k_on_o2"]
    assert m["x_o2"]["estimate"] == pytest.approx(2.0, abs=1e-9)
    assert m["intercept"]["estimate"] == pytest.approx(0.2, abs=1e-9)
    assert m["r_squared"] == pytest.approx(1.0)
    small = next(s for s in out["strata"] if s["pressure_cluster"] == "~0.7 atm")
    assert small["computable"] is False and "n >= 8" in small["abstention_reason"]
    assert any("CO2_added" in k for k in out["excluded"])


# ------------------------------------------------------------------ real PSI-69 data (skips without raw file)


@pytest.fixture(scope="module")
def real_runs():
    from fastapi import HTTPException

    from app.api.physics_routes import _data

    try:
        return _data()
    except HTTPException:
        pytest.skip("raw PSI-69 table not present (gitignored)")


def test_real_d2_consistency_regression(real_runs):
    a = p.d2_consistency(real_runs)
    assert a["n_runs"] == 154 and sum(a["excluded"].values()) == 274 - 154
    h, m = a["by_fuel"]["Heptane"], a["by_fuel"]["Methanol"]
    assert (h["n"], m["n"]) == (54, 100)
    assert round(h["median"], 3) == 0.949 and round(m["median"], 3) == 0.951
    assert "PSI-69-r130" in a["flagged_for_review"]  # FLEX-130: the known short, translated burn


def test_real_oxygen_effect_regression(real_runs):
    out = p.oxygen_effect(real_runs)
    ok = [s for s in out["strata"] if s["computable"]]
    assert {(s["fuel"], s["support_mode"], s["n"]) for s in ok} == {
        ("Heptane", "free_floating", 22),
        ("Methanol", "free_floating", 31),
    }
    for s in ok:
        lo, hi = s["model_k_on_o2"]["x_o2"]["ci95"]
        assert 0 < lo < hi  # positive association within these strata (descriptive)


# ------------------------------------------------------------------ API


def test_api_endpoints_and_method_cards(real_runs):
    c = TestClient(app)
    r = c.get("/api/v1/physics/d2-consistency", params={"fuel": "Methanol"})
    assert r.status_code == 200 and set(r.json()["by_fuel"]) == {"Methanol"}
    assert c.get("/api/v1/physics/d2-consistency", params={"fuel": "Ethanol"}).status_code == 422
    assert c.get("/api/v1/physics/d2-consistency", params={"diameter_halfwidth_mm": -1}).status_code == 422
    assert c.get("/api/v1/physics/oxygen-effect").status_code == 200
    ids = {m["method_id"] for m in c.get("/api/v1/methods").json()}
    assert {"flex.d2_consistency_of_reported_values", "flex.oxygen_effect_on_reported_k"} <= ids


# ------------------------------------------------------------------ edge cases and determinism


def test_ratio_interval_edge_cases():
    # D0 and Dext intervals overlap -> lower bound clipped at 0 (never negative)
    lo, hi = p.ratio_interval(1.0, 0.99, 0.5, 1.0, 0.01, 0.01, 0.0, 0.0)
    assert lo == 0.0 and hi > 0
    # K or burn-time interval reaching zero -> unbounded upper limit, not a division error
    assert p.ratio_interval(2.0, 1.0, 0.005, 6.0, 0.0, 0.0, 0.005, 0.0)[1] == float("inf")
    assert p.ratio_interval(2.0, 1.0, 0.5, 0.05, 0.0, 0.0, 0.0, 0.05)[1] == float("inf")


def test_empty_and_tiny_inputs_abstain_instead_of_guessing():
    empty = p.d2_consistency([])
    assert empty["n_runs"] == 0 and empty["by_fuel"] == {} and empty["flagged_for_review"] == []
    tiny = p.d2_consistency([run(i) for i in range(1, 4)])  # n = 3 < 5
    assert tiny["by_fuel"]["Heptane"]["median_ci95"] is None
    assert p.oxygen_effect([])["strata"] == []


def test_fuel_filter_and_non_physical_rows():
    runs = [run(1), run(2, fuel="Methanol"), run(3, d0="1.00", dext="1.50"), run(4, k="0")]
    a = p.d2_consistency(runs, fuel="Heptane")
    assert {x["fuel"] for x in a["runs"]} == {"Heptane"} and a["n_runs"] == 1
    assert sum(a["excluded"].values()) == 2  # Dext >= D0 and K = 0 are counted, not computed


def test_invalid_pressure_excludes_a_run_from_the_o2_strata():
    o2s = [0.15, 0.15, 0.21, 0.21, 0.25, 0.25, 0.30, 0.30]
    runs = [run(i, k=f"{0.2 + 2.0 * x:.2f}", o2=f"{x:.2f}") for i, x in enumerate(o2s, 1)]
    bad = run(99, o2="0.30", k="0.80")
    bad.raw[p.PRESSURE], bad.values[p.PRESSURE] = "0", 0.0
    bad.field_flags[p.PRESSURE] = ["invalid_nonpositive_pressure"]
    out = p.oxygen_effect([*runs, bad])
    assert out["excluded"] == {"missing_or_flagged": 1}
    assert out["strata"][0]["n"] == 8


def test_outputs_are_deterministic_across_calls(real_runs):
    assert p.d2_consistency(real_runs) == p.d2_consistency(real_runs)
    assert p.oxygen_effect(real_runs) == p.oxygen_effect(real_runs)


def test_api_returns_503_when_data_cannot_be_verified(monkeypatch):
    from app.analysis import flex_run_level as fx
    from app.api import physics_routes

    def broken():
        raise fx.IntegrityError("hash mismatch")

    monkeypatch.setattr(physics_routes, "_runs", broken)
    c = TestClient(app)
    r = c.get("/api/v1/physics/d2-consistency")
    assert r.status_code == 503 and "hash mismatch" in r.json()["detail"]
    assert c.get("/api/v1/physics/oxygen-effect").status_code == 503
