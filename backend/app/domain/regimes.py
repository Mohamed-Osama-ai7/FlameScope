"""Combustion-regime vocabulary.

FLEX, BASS-II and SAFFIRE are treated as *distinct* regimes. The outcome vocabulary below is a
controlled list of variable names the platform is allowed to attach to each regime. It is a
software contract, not a claim that every variable exists in the NASA source files; each variable
must still be verified against the acquired artifacts (see docs/03_scientific_gates.md).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CombustionRegime(str, Enum):
    FLEX_DROPLET = "flex_droplet"
    BASS_II_SOLID = "bass_ii_solid"
    SAFFIRE_SPACECRAFT_SCALE = "saffire_spacecraft_scale"


class Dimension(str, Enum):
    LENGTH = "length"
    LENGTH2_PER_TIME = "length^2/time"
    LENGTH_PER_TIME = "length/time"
    TIME = "time"
    PRESSURE = "pressure"
    DIMENSIONLESS = "dimensionless"
    ACCELERATION_RATIO = "g_ratio"


# Unit symbol -> physical dimension. Units are never converted silently; this table only decides
# whether two quantities *could* be compared after an explicit, documented conversion.
UNIT_DIMENSIONS: dict[str, Dimension] = {
    "mm": Dimension.LENGTH,
    "m": Dimension.LENGTH,
    "mm^2/s": Dimension.LENGTH2_PER_TIME,
    "m^2/s": Dimension.LENGTH2_PER_TIME,
    "mm/s": Dimension.LENGTH_PER_TIME,
    "cm/s": Dimension.LENGTH_PER_TIME,
    "m/s": Dimension.LENGTH_PER_TIME,
    "s": Dimension.TIME,
    "kPa": Dimension.PRESSURE,
    "mmHg": Dimension.PRESSURE,
    "atm": Dimension.PRESSURE,
    "psia": Dimension.PRESSURE,
    "1": Dimension.DIMENSIONLESS,
    "mole_fraction": Dimension.DIMENSIONLESS,
    "g": Dimension.ACCELERATION_RATIO,
}


class VariableDefinition(BaseModel):
    name: str
    dimension: Dimension
    description: str
    environmental: bool = False


VARIABLES: dict[str, VariableDefinition] = {
    v.name: v
    for v in [
        VariableDefinition(
            name="burning_rate_constant_mm2_s",
            dimension=Dimension.LENGTH2_PER_TIME,
            description=(
                "Burning-rate constant K as REPORTED by the source. For PSI-69 / NASA/TP-2015-216046 "
                "Table IX: average K from a linear fit of D^2 vs t from shortly after ignition to "
                "extinction (fit performed by the FLEX team, not by FlameScope)."
            ),
        ),
        VariableDefinition(
            name="burning_rate_constant_d2_fit_mm2_s",
            dimension=Dimension.LENGTH2_PER_TIME,
            description=(
                "Burning-rate constant CALCULATED by FlameScope's d^2-law tool from a D(t) series "
                "over a caller-declared window. Never pooled with reported values."
            ),
        ),
        VariableDefinition(
            name="initial_droplet_diameter",
            dimension=Dimension.LENGTH,
            description="Droplet diameter at the start of the analysed window.",
        ),
        VariableDefinition(
            name="extinction_diameter",
            dimension=Dimension.LENGTH,
            description="Droplet diameter at flame extinction.",
        ),
        VariableDefinition(
            name="flame_spread_rate",
            dimension=Dimension.LENGTH_PER_TIME,
            description=(
                "Rate of flame-front advance over a solid surface. Defined per apparatus, "
                "geometry and flow direction; BASS-II and SAFFIRE values are not interchangeable."
            ),
        ),
        VariableDefinition(
            name="forced_flow_velocity",
            dimension=Dimension.LENGTH_PER_TIME,
            description="Imposed gas-flow velocity past the sample.",
            environmental=True,
        ),
        VariableDefinition(
            name="ambient_pressure",
            dimension=Dimension.PRESSURE,
            description="Chamber/enclosure total pressure.",
            environmental=True,
        ),
        VariableDefinition(
            name="ambient_oxygen_mole_fraction",
            dimension=Dimension.DIMENSIONLESS,
            description="Oxygen mole fraction of the ambient atmosphere.",
            environmental=True,
        ),
        VariableDefinition(
            name="ambient_nitrogen_mole_fraction",
            dimension=Dimension.DIMENSIONLESS,
            description="Nitrogen mole fraction of the ambient atmosphere.",
            environmental=True,
        ),
        VariableDefinition(
            name="ambient_helium_mole_fraction",
            dimension=Dimension.DIMENSIONLESS,
            description="Helium (diluent/suppressant) mole fraction of the ambient atmosphere.",
            environmental=True,
        ),
        VariableDefinition(
            name="co2_mole_fraction",
            dimension=Dimension.DIMENSIONLESS,
            description=(
                "CO2 (diluent/suppressant) ambient mole fraction. PSI-69 header 'CO' resolved to "
                "CO2 by NASA/TP-2015-216046 Table IX and Appendix A.1 (see app/domain/flex_schema.py)."
            ),
            environmental=True,
        ),
        VariableDefinition(
            name="gravity_level",
            dimension=Dimension.ACCELERATION_RATIO,
            description="Residual gravity level relative to Earth gravity.",
            environmental=True,
        ),
    ]
}

_ENVIRONMENT = {n for n, v in VARIABLES.items() if v.environmental}

REGIME_VARIABLES: dict[CombustionRegime, frozenset[str]] = {
    CombustionRegime.FLEX_DROPLET: frozenset(
        {
            "burning_rate_constant_mm2_s",
            "burning_rate_constant_d2_fit_mm2_s",
            "initial_droplet_diameter",
            "extinction_diameter",
        }
        | _ENVIRONMENT
    ),
    CombustionRegime.BASS_II_SOLID: frozenset({"flame_spread_rate"} | _ENVIRONMENT),
    CombustionRegime.SAFFIRE_SPACECRAFT_SCALE: frozenset({"flame_spread_rate"} | _ENVIRONMENT),
}

# Minimum recorded conditions before two observations can be called "direct" or a "controlled
# variation". Provisional: the science lead must confirm these against the actual source tables.
REQUIRED_CONDITIONS: dict[CombustionRegime, frozenset[str]] = {
    # FLEX varied diluents (N2/He/CO2) deliberately; runs with different dilution are not "direct".
    CombustionRegime.FLEX_DROPLET: frozenset(
        {
            "ambient_pressure",
            "ambient_oxygen_mole_fraction",
            "ambient_nitrogen_mole_fraction",
            "ambient_helium_mole_fraction",
            "co2_mole_fraction",
        }
    ),
    CombustionRegime.BASS_II_SOLID: frozenset(
        {"ambient_pressure", "ambient_oxygen_mole_fraction", "forced_flow_velocity"}
    ),
    CombustionRegime.SAFFIRE_SPACECRAFT_SCALE: frozenset(
        {"ambient_pressure", "ambient_oxygen_mole_fraction", "forced_flow_velocity"}
    ),
}

REGIME_DESCRIPTIONS: dict[CombustionRegime, str] = {
    CombustionRegime.FLEX_DROPLET: (
        "Isolated liquid-fuel droplet combustion (FLEX, PSI-69; ISS CIR/MDCA)."
    ),
    CombustionRegime.BASS_II_SOLID: (
        "Small-sample solid-fuel ignition, flame spread and extinction in low-speed forced flow "
        "(BASS-II, PSI-25; ISS Microgravity Science Glovebox)."
    ),
    CombustionRegime.SAFFIRE_SPACECRAFT_SCALE: (
        "Large-scale solid-fuel fire growth inside an uncrewed spacecraft module "
        "(Saffire, PSI-98 candidate; Cygnus). PSI-98 metadata must be verified first."
    ),
}


# Same physical quantity, different value origin (reported by source vs calculated here). Allowed only
# as a cross-check (contextual), never pooled on one axis as if they were the same measurement.
CROSS_CHECK_PAIRS: frozenset[frozenset[str]] = frozenset(
    {frozenset({"burning_rate_constant_mm2_s", "burning_rate_constant_d2_fit_mm2_s"})}
)


def unit_dimension(unit: str) -> Dimension | None:
    return UNIT_DIMENSIONS.get(unit)
