"""Controlled vocabulary seeded into the ``variables`` and ``units`` tables.

Single source of truth: app.domain.regimes (owned by the science workstream). This module only adds
variables that a loaded source column needs and the domain list does not yet define; each addition is
marked ``defined_in = app.data_platform.vocabulary`` so the science lead can adopt or rename it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.regimes import UNIT_DIMENSIONS, VARIABLES, Dimension

DOMAIN = "app.domain.regimes"
PLATFORM = "app.data_platform.vocabulary"


@dataclass(frozen=True)
class VariableSpec:
    name: str
    dimension: str
    description: str
    environmental: bool
    defined_in: str


# Present in PSI-69 ('Burn time; s', docs: data/metadata/variable_dictionary.csv) but not in the domain list.
PLATFORM_VARIABLES: tuple[VariableSpec, ...] = (
    VariableSpec(
        name="burn_time",
        dimension=Dimension.TIME.value,
        description=(
            "Burn duration as REPORTED by the source table (PSI-69 'Burn time; s'). Values written as "
            "'~x' are kept with value_status=approximate."
        ),
        environmental=False,
        defined_in=PLATFORM,
    ),
)


def variable_specs() -> list[VariableSpec]:
    specs = [
        VariableSpec(v.name, v.dimension.value, v.description, v.environmental, DOMAIN)
        for v in VARIABLES.values()
    ]
    clash = {s.name for s in specs} & {p.name for p in PLATFORM_VARIABLES}
    if clash:  # the domain adopted the name: the domain definition wins, drop ours
        return specs + [p for p in PLATFORM_VARIABLES if p.name not in clash]
    return specs + list(PLATFORM_VARIABLES)


def unit_specs() -> dict[str, str]:
    return {symbol: dim.value for symbol, dim in UNIT_DIMENSIONS.items()}


def dimension_of_variable(name: str) -> str | None:
    return next((s.dimension for s in variable_specs() if s.name == name), None)
