"""Tests for corrections made in the FLEX scientific audit (docs/11_flex_scientific_audit.md)."""

import csv
import hashlib
import json
from collections import Counter

import pytest

from app.analysis import flex_run_level as fx
from app.api.routes import PROJECT_ROOT

META = PROJECT_ROOT / "data" / "metadata"
ENRICH = PROJECT_ROOT / "data" / "derived" / "flex_enrichment_v1.csv"
CAPS = PROJECT_ROOT / "data" / "derived" / "flex_enrichment_v1_captions.json"
V01 = PROJECT_ROOT / "reports" / "flex_run_level"
V01_SHA256 = {  # approved v0.1.0 baseline outputs must stay byte-identical
    # SHA-256 of the committed (LF) bytes, kept byte-exact by .gitattributes. The JSON pins were first taken
    # on a Windows CRLF working copy (summary 3969559d..., quality_report 89019788...); those equal the
    # SHA-256 of these same bytes with LF -> CRLF, so the approved content is unchanged.
    "summary.json": "199136152fd2f347893c25f9a95c6df65038c73615c30d297f51104b2db36fc3",
    "strata_results.csv": "abcec13b54267c47442fcc66760549136ad97b710b764ce9886c8e4c24d21d9d",
    "row_quality_table.csv": "a75d9bdf7fd0588578ee9335488a24f8e669a9b6ad2f5db4d3b8370ac34dd6d3",
    "quality_report.json": "672040d111fabdefa2a0c69019d11e21ea7543914a950cf6ba9af158d3b2f468",
    "descriptive_by_fuel.csv": "0d42722c996e35d381b5f1ec9d5c25b289ebc3fe95759a1f9863bad7d2ba437f",
}


def enrichment():
    with ENRICH.open(encoding="utf-8", newline="") as fh:
        return {int(r["psi_row"]): r for r in csv.DictReader(fh)}


# ---------------------------------------------------------------- enrichment / identity


def test_enrichment_covers_every_psi_row_with_unique_keys():
    e = enrichment()
    assert sorted(e) == list(range(1, 275))
    keys = [r["record_key"] for r in e.values()]
    assert len(set(keys)) == 274
    assert len({r["flex_test_number"] for r in e.values()}) == 274


def test_duplicate_source_identifier_kept_as_two_records():
    e = enrichment()
    dup = [r for r in e.values() if r["identifier"] == "193F001"]
    assert sorted(int(r["flex_test_number"]) for r in dup) == [70, 73]
    assert len({r["record_key"] for r in dup}) == 2


def test_psi_numbering_differs_from_report_numbering():
    e = enrichment()
    assert sum(int(r["flex_test_number"]) != k for k, r in e.items()) == 119
    assert int(e[156]["flex_test_number"]) == 157


def test_counts_reconciled_without_forcing():
    caps = json.loads(CAPS.read_text(encoding="utf-8"))
    assert {r["flex"] for r in caps["unmatched_table_ix_rows"]} == {216, 230}
    assert caps["flex_numbers_without_caption"] == [156, 205, 213, 228]
    rec = json.loads((META / "flex_report_reconciliation.json").read_text(encoding="utf-8"))
    assert rec["results"]["table_ix_printed_rows_visually_verified"] == 276
    assert any("284" in u for u in rec["unresolved"])


def test_support_modes_from_source_and_conflicts_marked():
    e = enrichment()
    assert e[130]["support_mode"] == "fiber_translated"
    assert e[53]["support_mode"] == "conflicting_sources"
    assert e[124]["support_mode"] == "conflicting_sources"
    assert Counter(r["support_mode"] for r in e.values())["free_floating"] == 209


def test_pressure_conflict_recorded_not_substituted():
    e = enrichment()
    assert "0.7 atm" in e[114]["pressure_source_conflict"]
    runs, _ = (
        fx.load_verified(
            PROJECT_ROOT / fx.manifest_entry(META / "artifact_manifest.csv")["relative_path"],
            META / "artifact_manifest.csv",
        )
        if _raw_present()
        else (None, None)
    )
    if runs is not None:
        r114 = next(r for r in runs if r.psi_row == 114)
        assert r114.values["ambient_pressure"] == 0.0 and not r114.usable("ambient_pressure")


def test_only_documented_tests_carry_contamination_flags():
    e = enrichment()
    flagged = {int(r["flex_test_number"]) for r in e.values() if r["documented_contamination_or_feature"]}
    assert flagged == {37, 88, 90, 109}
    assert all(r["coated_needle_period"] == "True" for r in e.values())  # report-wide condition, sec. 5.2
    assert {int(r["flex_test_number"]) for r in e.values() if r["shutter_1_30s_period"] == "True"} == set(
        range(1, 10)
    )


# ---------------------------------------------------------------- extinction-diameter semantics


def _run(dext_raw: str, test_end: str) -> fx.FlexRun:
    v, flags = fx.parse_value(dext_raw)
    return fx.FlexRun(
        psi_row=1,
        identifier="X",
        test_date="",
        test_time_gmt="",
        fuel="Heptane",
        test_end=test_end,
        raw={},
        values={"extinction_diameter": v},
        field_flags={"extinction_diameter": flags},
    )


@pytest.mark.parametrize(
    "raw,end,note,expected",
    [
        ("–", "Disruption", "", "not_applicable_no_extinction_per_A1"),
        ("–", "Completion", "", "not_applicable_no_extinction_per_A1"),
        ("–", "Extinction", "", "inconsistent_dash_with_extinction_end"),
        ("", "Extinction", "", "not_listed_insufficient_view_per_A1"),
        ("0", "Completion", "", "zero_semantics_unconfirmed"),
        ("1.2", "Disruption", "", "value_with_non_extinction_end_semantics_unclear"),
        (
            "1.2",
            "Extinction",
            "caption_mentions_extrapolation",
            "reported_extinction_extrapolation_noted_in_caption",
        ),
        ("1.2", "Extinction", "", "reported_extinction_no_extrapolation_noted"),
        ("1.2", "Extinction", None, "reported_extinction_extrapolation_unknown"),
    ],
)
def test_dext_origin_never_collapses_missingness(raw, end, note, expected):
    assert fx.classify_dext(_run(raw, end), note) == expected


def test_cluster_labels_use_nasa_nominal_levels():
    assert fx.cluster_label(526.3, 544.4).startswith("~0.7 atm nominal")
    assert fx.cluster_label(2318.8, 2319.9).startswith("~3.05 atm nominal")


# ---------------------------------------------------------------- real-data behaviour


def _raw_present() -> bool:
    return (PROJECT_ROOT / fx.manifest_entry(META / "artifact_manifest.csv")["relative_path"]).exists()


real = pytest.mark.skipif(not _raw_present(), reason="raw PSI-69 table not present (gitignored)")


@pytest.fixture(scope="module")
def real_runs():
    manifest = META / "artifact_manifest.csv"
    runs, _ = fx.load_verified(PROJECT_ROOT / fx.manifest_entry(manifest)["relative_path"], manifest)
    fx.attach_enrichment(runs, ENRICH)
    return runs


@real
def test_pressure_clusters_stable_across_gap_rules(real_runs):
    ps = fx._vals(real_runs, "ambient_pressure")
    ref = fx.pressure_clusters(ps, 100)
    assert len(ref) == 5
    for gap in (25, 50, 200):
        assert fx.pressure_clusters(ps, gap) == ref


@real
def test_no_stratum_pools_support_modes_or_fuels(real_runs):
    res = fx.run_analyses(real_runs)
    by_row = {r.psi_row: r for r in real_runs}
    for s in res["strata"]:
        rows = [by_row[n] for n in s["psi_rows"]]
        assert {r.support_mode for r in rows} == {s["stratum"]["support_mode"]}
        assert {r.fuel for r in rows} == {s["fuel"]}


@real
def test_flex130_value_retained_and_only_in_fiber_strata(real_runs):
    r130 = next(r for r in real_runs if r.flex_test_number == 130)
    assert r130.values["burning_rate_constant_mm2_s"] == 0.05  # source value retained
    res = fx.run_analyses(real_runs)
    for s in res["strata"]:
        if r130.psi_row in s["psi_rows"]:
            assert s["stratum"]["support_mode"] == "fiber_translated"
            assert r130.psi_row in s["sensitivity_rows"]


@real
def test_dext_analysis_uses_only_eligible_origin(real_runs):
    res = fx.run_analyses(real_runs)
    by_row = {r.psi_row: r for r in real_runs}
    for s in res["strata"]:
        if s["analysis"] == "A6_O2_vs_Dext":
            assert {by_row[n].dext_origin for n in s["psi_rows"]} == {
                "reported_extinction_no_extrapolation_noted"
            }


@real
def test_shutter_rows_produce_labelled_sensitivity(real_runs):
    res = fx.run_analyses(real_runs)
    hits = [s for s in res["strata"] if set(s["sensitivity_rows"]) & set(range(1, 10))]
    assert hits and all(s["rho_spearman"] is None or "rho_without_sensitivity_rows" in s for s in hits)


@real
def test_outcome_caveats_cite_contamination(real_runs):
    out = fx.run_analyses(real_runs)["outcomes"]
    assert "probably due" in out["contamination_caveats"]["Methanol"]
    assert "no conclusion" in out["contamination_caveats"]["Heptane"]


def test_v01_baseline_outputs_unchanged():
    for name, digest in V01_SHA256.items():
        assert hashlib.sha256((V01 / name).read_bytes()).hexdigest() == digest, name


def test_v02_summary_records_provenance_and_scope():
    path = PROJECT_ROOT / "reports" / "flex_run_level_v0.2" / "summary.json"
    s = json.loads(path.read_text(encoding="utf-8"))
    assert s["analysis_version"] == "0.2.0"
    assert s["enrichment"]["sha256"] == hashlib.sha256(ENRICH.read_bytes()).hexdigest()
    assert s["scope"]["psi_rows_analysed"] == 274 and s["scope"]["nasa_report_states_tests"] == 284
    assert s["sensitivity_reported_K_0.05_FLEX_130"]["primary_retains_source_value"] is True
    for chart in s["charts"]:
        for keys in chart["plotted_record_keys"].values():
            assert all(k.startswith("PSI69-r") for k in keys)
