"""Canonical PSI-69 FLEX mappings resolved by NASA/TP-2015-216046 (Appendix A.1, Table IX)."""
import csv
import json

import pytest

from app.api.routes import PROJECT_ROOT
from app.domain.comparison import ComparisonClass, ObservationDescriptor, validate_comparison
from app.domain.flex_schema import FLEX_COLUMNS, canonical_name
from app.domain.regimes import (
    REGIME_VARIABLES,
    VARIABLES,
    CombustionRegime,
    Dimension,
    unit_dimension,
)
from app.science.droplet import BurningRateResult

META = PROJECT_ROOT / "data" / "metadata"
RAW_FLEX = PROJECT_ROOT / "data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv"


def test_canonical_burning_rate_mapping_and_unit():
    m = FLEX_COLUMNS["Burning rate; mm"]
    assert canonical_name("Burning rate; mm") == "burning_rate_constant_mm2_s"
    assert m.unit == "mm^2/s" and unit_dimension(m.unit) is Dimension.LENGTH2_PER_TIME
    assert m.value_origin == "reported_in_source"
    assert "NASA/TP-2015-216046" in m.evidence and "Appendix A.1" in m.evidence


def test_canonical_co2_mapping():
    m = FLEX_COLUMNS["CO initial ambient composition; mole fraction"]
    assert m.canonical == "co2_mole_fraction" and m.unit == "mole_fraction"
    assert "Table IX" in m.evidence


def test_unknown_header_is_not_guessed():
    with pytest.raises(KeyError):
        canonical_name("Burning rate")


def test_canonical_names_are_in_flex_vocabulary_with_matching_dimension():
    for m in FLEX_COLUMNS.values():
        assert m.canonical in REGIME_VARIABLES[CombustionRegime.FLEX_DROPLET], m.canonical
        if m.unit:
            assert VARIABLES[m.canonical].dimension is unit_dimension(m.unit), m.canonical


def test_retired_ambiguous_names_are_gone():
    assert "burning_rate_constant" not in VARIABLES
    assert "ambient_carbon_dioxide_mole_fraction" not in VARIABLES


def test_raw_headers_preserved_unchanged():
    if not RAW_FLEX.exists():
        pytest.skip("raw PSI-69 table not present (gitignored); run fetch_psi_table.py")
    header = RAW_FLEX.read_bytes().split(b"\r\n", 1)[0].decode("cp1252").split(",")
    assert "Burning rate; mm" in header
    assert "CO initial ambient composition; mole fraction" in header
    assert set(FLEX_COLUMNS) <= set(header)


def test_dictionary_agrees_with_code_mapping():
    with (META / "variable_dictionary.csv").open(encoding="utf-8", newline="") as fh:
        rows = {r["source_column"]: r for r in csv.DictReader(fh) if r["source_id"] == "PSI-69"}
    for raw, m in FLEX_COLUMNS.items():
        assert rows[raw]["platform_variable"] == m.canonical
        assert rows[raw]["value_origin"] == "reported_in_source"
    for raw in ("Burning rate; mm", "CO initial ambient composition; mole fraction"):
        assert rows[raw]["mapping_status"] == "RESOLVED"
        assert "NASA/TP-2015-216046" in rows[raw]["evidence_reference"]
        assert "ntrs.nasa.gov" in rows[raw]["evidence_reference"]
    assert rows["Burning rate; mm"]["platform_unit"] == "mm^2/s"


def test_reported_and_calculated_k_are_distinct():
    fields = BurningRateResult.model_fields
    assert fields["output_variable"].default == "burning_rate_constant_d2_fit_mm2_s"
    assert fields["value_origin"].default == "calculated_from_diameter_history"
    assert FLEX_COLUMNS["Burning rate; mm"].canonical != "burning_rate_constant_d2_fit_mm2_s"


def test_reported_vs_calculated_k_is_cross_check_only():
    def obs(var: str) -> ObservationDescriptor:
        return ObservationDescriptor(
            investigation_id="PSI-69",
            regime=CombustionRegime.FLEX_DROPLET,
            variable=var,
            unit="mm^2/s",
        )

    r = validate_comparison(
        obs("burning_rate_constant_mm2_s"), obs("burning_rate_constant_d2_fit_mm2_s")
    )
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert not r.shared_axis_allowed
    assert any("cross-check only" in reason for reason in r.reasons)


def test_reconciliation_record_does_not_force_counts():
    rec = json.loads((META / "flex_report_reconciliation.json").read_text(encoding="utf-8"))
    res = rec["results"]
    assert res["psi_rows"] == 274 and res["psi_rows_exactly_matching_a_table_ix_row"] == 274
    assert rec["reference"]["report_id"] == "NASA/TP-2015-216046"
    assert any("284" in u for u in rec["unresolved"])
    assert {r["flex"] for r in res["table_ix_rows_absent_from_psi"]} == {"FLEX-216", "FLEX-230"}
