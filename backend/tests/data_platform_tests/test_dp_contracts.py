"""Pure contracts: identifiers, vocabulary, column mapping, date parsing, registry status (no database)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.data_platform import ids
from app.data_platform.extract_flex import column_specs, parse_test_date
from app.data_platform.vocabulary import PLATFORM_VARIABLES, dimension_of_variable, unit_specs, variable_specs
from app.domain.flex_schema import FLEX_COLUMNS
from app.domain.regimes import UNIT_DIMENSIONS, VARIABLES
from app.domain.sources import SourceRecord, VerificationStatus, official_resource_recorded

SHA = "a" * 64


def test_ids_are_deterministic_and_location_specific():
    assert ids.measurement_id(SHA, 1, "Fuel") == ids.measurement_id(SHA, 1, "Fuel")
    assert ids.measurement_id(SHA, 1, "Fuel") != ids.measurement_id(SHA, 2, "Fuel")
    assert ids.measurement_id(SHA, 1, "Fuel") != ids.measurement_id(SHA, 1, "Test end")
    assert ids.measurement_id(SHA, 1, "Fuel") != ids.measurement_id("b" * 64, 1, "Fuel")
    assert ids.artifact_id(SHA, "a/b.csv") == ids.artifact_id(SHA, "a/b.csv")
    assert ids.extraction_run_id("x", "1", ["b", "a"]) == ids.extraction_run_id("x", "1", ["a", "b"])
    assert ids.extraction_run_id("x", "1", ["a"]) != ids.extraction_run_id("x", "2", ["a"])
    assert isinstance(ids.artifact_id(SHA, "p"), uuid.UUID)


def test_run_id_is_url_safe_and_zero_padded():
    assert ids.run_id("PSI-69", 1) == "PSI-69-r001"
    assert ids.run_id("PSI-69", 274) == "PSI-69-r274"


def test_vocabulary_covers_domain_and_platform_variables():
    names = {v.name for v in variable_specs()}
    assert set(VARIABLES) <= names
    assert {p.name for p in PLATFORM_VARIABLES} <= names
    assert len(names) == len(variable_specs()), "duplicate variable names"
    assert unit_specs() == {k: v.value for k, v in UNIT_DIMENSIONS.items()}


def test_flex_column_specs_cover_every_numeric_column_with_consistent_dimensions():
    specs = column_specs()
    assert {s.raw_header for s in specs} == set(FLEX_COLUMNS) | {"Burn time; s"}
    units = unit_specs()
    for s in specs:
        assert s.unit in units, s
        assert dimension_of_variable(s.variable) == units[s.unit], s
    k = next(s for s in specs if s.variable == "burning_rate_constant_mm2_s")
    assert (k.original_unit_label, k.unit) == ("mm", "mm^2/s")  # header lost '2/s'; resolved by NASA/TP
    assert "NASA/TP-2015-216046" in k.unit_evidence


@pytest.mark.parametrize(
    ("raw", "expected", "flags"),
    [
        ("3/5/2009", date(2009, 3, 5), []),
        ("12/8/2011", date(2011, 12, 8), []),
        ("3/23/10", date(2010, 3, 23), ["test_date_two_digit_year_assumed_20yy"]),
        ("", None, ["missing_test_date"]),
        ("2/30/2010", None, ["unparseable_test_date"]),
        ("2010-03-23", None, ["unparseable_test_date"]),
    ],
)
def test_parse_test_date(raw, expected, flags):
    assert parse_test_date(raw) == (expected, flags)


def test_resource_recorded_status_needs_url_and_time_and_is_not_evidence():
    base = dict(
        source_id="R",
        source_title="PSI Data Repository: Combustion Science",
        source_type="NASA_CHALLENGE_RESOURCE",
        official_challenge_resource="YES",
        verification_status="RESOURCE_RECORDED",
    )
    with pytest.raises(ValueError, match="RESOURCE_RECORDED requires source_url, retrieved_at_utc"):
        SourceRecord.model_validate(base)
    rec = SourceRecord.model_validate(
        {
            **base,
            "source_url": "https://psi.nasa.gov/physci/repo/search?q=combustion",
            "retrieved_at_utc": "x",
        }
    )
    assert rec.verification_status is VerificationStatus.RESOURCE_RECORDED
    assert not rec.usable_as_evidence
    # A catalogue alone does not satisfy the gate: an acquired, hashed child file is required.
    assert not official_resource_recorded([rec])


def test_repository_registry_records_official_resource_with_evidence():
    from app.api.routes import REGISTRY_PATH
    from app.domain.sources import find_source, load_registry

    records = load_registry(REGISTRY_PATH)
    gate = find_source(records, "CHALLENGE-RESOURCE-01")
    assert gate is not None and gate.verification_status is VerificationStatus.RESOURCE_RECORDED
    assert gate.source_url == "https://psi.nasa.gov/physci/repo/search?q=combustion"
    assert gate.official_challenge_resource
    psi69 = find_source(records, "PSI-69")
    assert psi69 is not None and psi69.official_challenge_resource and psi69.usable_as_evidence
    psi98 = find_source(records, "PSI-98")
    assert psi98 is not None and psi98.verification_status is VerificationStatus.QUARANTINED
    assert official_resource_recorded(records)
