"""FLEX run-level analysis tests.

Synthetic tables below are TEST INPUTS ONLY (values are invented and never presented as NASA data);
the real-data tests run only when the verified PSI-69 file is present locally.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.analysis import flex_run_level as fx
from app.api.routes import PROJECT_ROOT

HEADER = [
    "FLEX Test #", "FLEX Identifier", "Test Date", "Test GMT", "Fuel", "Ambient pressure; mmHg",
    "O initial ambient composition; mole fraction", "N initial ambient composition; mole fraction",
    "CO initial ambient composition; mole fraction", "He initial ambient composition; mole fraction",
    "Droplet initial diameter; mm", "Visible flame extinction diameter; mm", "Burning rate; mm",
    "Burn time; s", "Test end",
]
D = "–"


def synthetic_rows() -> list[list[str]]:
    rows = []
    for i, o2 in enumerate([0.15, 0.17, 0.19, 0.21, 0.23, 0.25], start=1):
        rows.append([str(i), f"M{i:03d}", "1/1/2010", "1:00:00", "Methanol", "760", str(o2),
                     f"{1 - o2:.2f}", "0", "0", "3.0", "1.0", f"{0.3 + o2:.2f}", "5", "Extinction"])
    for i, o2 in enumerate([0.15, 0.17, 0.19, 0.21, 0.23], start=7):
        rows.append([str(i), f"H{i:03d}", "1/2/2010", "2:00:00", "Heptane", "761", str(o2),
                     f"{1 - o2:.2f}", "0", "0", "3.0", "1.5", f"{0.9 - o2:.2f}", "5", "Extinction"])
    rows[0][12] = ""          # missing K (blank)
    rows[1][10] = D           # missing D0 (en-dash marker)
    rows[2][13] = "~6"        # approximate burn time
    rows[3][5] = "0"          # invalid pressure
    rows[4][1] = rows[5][1]   # duplicate identifier (Methanol)
    rows[4][3] = rows[5][3]   # ... with identical timestamp
    rows[6][11] = "0"         # zero extinction diameter (Heptane)
    return rows


def to_bytes(rows: list[list[str]]) -> bytes:
    text = "\r\n".join(",".join(r) for r in [HEADER, *rows]) + "\r\n"
    return text.encode("cp1252")


@pytest.fixture
def runs():
    return fx.parse_table(to_bytes(synthetic_rows()))


def by_row(runs, n):
    return next(r for r in runs if r.psi_row == n)


def test_all_rows_preserved(runs):
    assert len(runs) == 11
    assert [r.psi_row for r in runs] == list(range(1, 12))


def test_missing_values_flagged_not_invented(runs):
    r1, r2 = by_row(runs, 1), by_row(runs, 2)
    assert r1.values["burning_rate_constant_mm2_s"] is None
    assert "missing_blank" in r1.field_flags["burning_rate_constant_mm2_s"]
    assert r2.values["initial_droplet_diameter"] is None
    assert "missing_dash_marker" in r2.field_flags["initial_droplet_diameter"]
    assert not r1.usable("burning_rate_constant_mm2_s")


def test_approximate_value_kept_with_flag(runs):
    r3 = by_row(runs, 3)
    assert r3.values["burn_time_s"] == 6.0
    assert "approximate" in r3.field_flags["burn_time_s"]


def test_invalid_pressure_flagged_and_excluded_with_reason(runs):
    r4 = by_row(runs, 4)
    assert r4.values["ambient_pressure"] == 0.0  # raw value retained
    assert "invalid_nonpositive_pressure" in r4.field_flags["ambient_pressure"]
    assert not r4.usable("ambient_pressure") and r4.pressure_cluster is None
    res = fx.run_analyses(runs)
    assert res["exclusions"]["A1_O2_vs_K"]["Methanol"]["P_mmHg:invalid_nonpositive_pressure"] == 1
    assert res["exclusions"]["A1_O2_vs_K"]["Methanol"]["K_reported_mm2_s:missing_blank"] == 1


def test_duplicate_identifiers_retained(runs):
    dups = [r for r in runs if "duplicate_source_identifier" in r.row_flags]
    assert {r.psi_row for r in dups} == {5, 6}
    assert len({(r.identifier, r.test_time_gmt) for r in dups}) == 1  # same id + time, both kept


def test_zero_extinction_diameter_flagged(runs):
    r7 = by_row(runs, 7)
    assert "zero_value_meaning_unconfirmed" in r7.field_flags["extinction_diameter"]
    res = fx.run_analyses(runs)
    assert res["exclusions"]["A6_O2_vs_Dext"]["Heptane"]["dext_origin:zero_semantics_unconfirmed"] == 1


def test_fuels_never_pooled(runs):
    res = fx.run_analyses(runs)
    for s in res["strata"]:
        fuels = {by_row(runs, n).fuel for n in s["psi_rows"]}
        assert fuels == {s["fuel"]}
    assert res["cross_fuel_gate_check"]["shared_axis_allowed_pairs"] == 0


def test_o2_strata_use_only_n2_balance(runs):
    res = fx.run_analyses(runs)
    a1 = [s for s in res["strata"] if s["analysis"] == "A1_O2_vs_K"]
    assert a1 and all(s["stratum"]["diluent_family"] == "N2_only" for s in a1)
    meth = next(s for s in a1 if s["fuel"] == "Methanol")
    assert meth["n"] == 4  # 6 rows - missing K (row 1) - invalid pressure (row 4)


def test_spearman_basic_and_minimum_n():
    assert fx.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    assert fx.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert fx.spearman([1, 2, 3, 4], [1, 2, 3, 4]) is None  # n < 5: not reported
    assert fx.spearman([1, 1, 1, 1, 1], [1, 2, 3, 4, 5]) is None


def test_sha_mismatch_blocks_analysis():
    data = to_bytes(synthetic_rows())
    entry = {"sha256": "0" * 64, "byte_size": str(len(data)), "relative_path": "x"}
    with pytest.raises(fx.IntegrityError):
        fx.verify_artifact(data, entry)
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    assert fx.verify_artifact(data, entry) == entry["sha256"]


def test_unmapped_header_rejected():
    bad = to_bytes(synthetic_rows()).replace(b"Burning rate; mm", b"Burning rate")
    with pytest.raises(fx.IntegrityError):
        fx.parse_table(bad)


def test_d2_law_calculator_not_used():
    src = Path(fx.__file__).read_text(encoding="utf-8")
    assert "fit_burning_rate_constant" not in src and "app.science.droplet" not in src


# ---------------------------------------------------------------- real verified artifact

MANIFEST = PROJECT_ROOT / "data" / "metadata" / "artifact_manifest.csv"


def _real_path():
    return PROJECT_ROOT / fx.manifest_entry(MANIFEST)["relative_path"]


real = pytest.mark.skipif(not _real_path().exists(), reason="raw PSI-69 table not present (gitignored)")


@real
def test_real_table_verified_and_complete():
    runs, entry = fx.load_verified(_real_path(), MANIFEST)
    assert len(runs) == 274
    assert {r.fuel for r in runs} == {"Methanol", "Heptane"}
    assert sum(r.fuel == "Methanol" for r in runs) == 157
    dup = sorted(r.psi_row for r in runs if "duplicate_source_identifier" in r.row_flags)
    assert dup == [70, 73]
    assert [r.psi_row for r in runs if not r.usable("ambient_pressure")] == [114]


@real
def test_runner_outputs_are_reproducible(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "run_flex_analysis", PROJECT_ROOT / "backend" / "scripts" / "run_flex_analysis.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_flex_analysis"] = mod
    spec.loader.exec_module(mod)
    a, b = tmp_path / "a", tmp_path / "b"
    assert mod.main(["--out", str(a)]) == 0 and mod.main(["--out", str(b)]) == 0
    for name in ("summary.json", "strata_results.csv", "row_quality_table.csv"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    summary = json.loads((a / "summary.json").read_text(encoding="utf-8"))
    assert summary["source"]["sha256_verified_before_analysis"] is True
    assert summary["scope"]["psi_rows_analysed"] == 274
    assert summary["scope"]["nasa_report_states_tests"] == 284
    assert "NOT used" in summary["value_origin"]
    rows = (a / "row_quality_table.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 275  # header + every PSI row
