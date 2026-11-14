"""Comparison-gate tests. Descriptors are synthetic test inputs, not NASA measurements."""
from app.domain.comparison import (
    ComparisonClass,
    Condition,
    ObservationDescriptor,
    validate_comparison,
)
from app.domain.regimes import CombustionRegime

FLEX = CombustionRegime.FLEX_DROPLET
BASS = CombustionRegime.BASS_II_SOLID
SAFFIRE = CombustionRegime.SAFFIRE_SPACECRAFT_SCALE


def flex(**overrides):
    base = dict(
        investigation_id="PSI-69",
        regime=FLEX,
        variable="burning_rate_constant_mm2_s",
        unit="mm^2/s",
        material_or_fuel="fuel-A",
        apparatus="MDCA",
        conditions={
            "ambient_pressure": Condition(value=1.0, unit="atm"),
            "ambient_oxygen_mole_fraction": Condition(value=0.21, unit="mole_fraction"),
            "ambient_nitrogen_mole_fraction": Condition(value=0.79, unit="mole_fraction"),
            "ambient_helium_mole_fraction": Condition(value=0.0, unit="mole_fraction"),
            "co2_mole_fraction": Condition(value=0.0, unit="mole_fraction"),
        },
    )
    base.update(overrides)
    return ObservationDescriptor(**base)


def flex_conditions(**changes):
    conds = dict(flex().conditions)
    conds.update(changes)
    return conds


def solid(regime, **overrides):
    base = dict(
        investigation_id="PSI-25" if regime is BASS else "PSI-98",
        regime=regime,
        variable="flame_spread_rate",
        unit="mm/s",
        material_or_fuel="material-X",
        apparatus="rig",
        conditions={
            "ambient_pressure": Condition(value=1.0, unit="atm"),
            "ambient_oxygen_mole_fraction": Condition(value=0.21, unit="mole_fraction"),
            "forced_flow_velocity": Condition(value=100, unit="mm/s"),
        },
    )
    base.update(overrides)
    return ObservationDescriptor(**base)


def test_identical_setup_is_direct():
    r = validate_comparison(flex(), flex())
    assert r.classification is ComparisonClass.DIRECT
    assert r.shared_axis_allowed


def test_single_condition_change_is_controlled_variation():
    b = flex(conditions=flex_conditions(ambient_pressure=Condition(value=0.5, unit="atm")))
    r = validate_comparison(flex(), b)
    assert r.classification is ComparisonClass.CONTROLLED_VARIATION
    assert r.differing == ["ambient_pressure"]


def test_droplet_k_vs_flame_spread_is_not_comparable():
    r = validate_comparison(flex(), solid(BASS))
    assert r.classification is ComparisonClass.NOT_COMPARABLE
    assert not r.shared_axis_allowed


def test_flame_spread_cannot_be_attached_to_flex_regime():
    r = validate_comparison(flex(variable="flame_spread_rate", unit="mm/s"), flex())
    assert r.classification is ComparisonClass.NOT_COMPARABLE


def test_bass_vs_saffire_flame_spread_is_only_contextual():
    r = validate_comparison(solid(BASS), solid(SAFFIRE))
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert not r.shared_axis_allowed
    assert any("different combustion regimes" in reason for reason in r.reasons)


def test_wrong_unit_dimension_is_rejected():
    r = validate_comparison(flex(unit="mm/s"), flex())
    assert r.classification is ComparisonClass.NOT_COMPARABLE


def test_same_dimension_different_unit_is_not_silently_converted():
    r = validate_comparison(flex(), flex(unit="m^2/s"))
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert not r.shared_axis_allowed


def test_missing_required_conditions_prevent_direct_claim():
    r = validate_comparison(flex(conditions={}), flex(conditions={}))
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert "ambient_pressure" in r.unknown


def test_different_fuel_is_not_controlled_variation():
    r = validate_comparison(flex(), flex(material_or_fuel="fuel-B"))
    assert r.classification is ComparisonClass.CONTEXTUAL


def test_flex_different_diluent_is_not_direct():
    b = flex(conditions=flex_conditions(
        ambient_helium_mole_fraction=Condition(value=0.2, unit="mole_fraction"),
        ambient_nitrogen_mole_fraction=Condition(value=0.59, unit="mole_fraction"),
    ))
    r = validate_comparison(flex(), b)
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert set(r.differing) == {"ambient_helium_mole_fraction", "ambient_nitrogen_mole_fraction"}


def test_flex_missing_diluent_record_prevents_direct():
    conds = flex_conditions()
    del conds["ambient_helium_mole_fraction"]
    r = validate_comparison(flex(conditions=conds), flex(conditions=conds))
    assert r.classification is ComparisonClass.CONTEXTUAL
    assert "ambient_helium_mole_fraction" in r.unknown
