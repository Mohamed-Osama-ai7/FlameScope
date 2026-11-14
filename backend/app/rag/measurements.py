"""PSI-69 measurements with Data-Platform-compatible identity, quality flags and an evidence status.

The values, flags and `usable_for_analysis` rule come from the project's verified FLEX loader
(app.analysis.flex_run_level), which the Data Platform extractor (extract_flex 1.0.0) also uses; ids and
locators follow the platform contract (app/rag/ids.py). No value is computed, rounded or imputed here.

Evidence status (stricter than `usable_for_analysis`, never looser):
* CLEAN     - usable value with no quality flag: may be stated as a reported value.
* QUALIFIED - usable value with a scientific flag (approximate, zero meaning unconfirmed, Dext > D0,
              composition sum deviation, known caveat): may be stated only together with the qualifier.
* INVALID   - value present but not usable for analysis: may be mentioned only as "FLAGGED INVALID".
* MISSING   - no value in the source (blank, dash marker, not a number): stated as missing, never filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import quote, urlencode

from app.analysis import flex_run_level as fx
from app.domain.flex_schema import FLEX_COLUMNS
from app.rag import ids

SOURCE_ID = "PSI-69"
BURN_TIME_HEADER = "Burn time; s"
NONNEGATIVE = {
    "initial_droplet_diameter",
    "extinction_diameter",
    "burning_rate_constant_mm2_s",
    "burn_time_s",
}
MISSING_FLAGS = {"missing_blank", "missing_dash_marker", "unparseable"}
COMPOSITION = (
    "ambient_oxygen_mole_fraction",
    "ambient_nitrogen_mole_fraction",
    "co2_mole_fraction",
    "ambient_helium_mole_fraction",
)
# row-level flags that qualify specific measurements
ROW_FLAG_TARGETS = {
    "dext_exceeds_d0": ("extinction_diameter", "initial_droplet_diameter"),
    "composition_sum_deviation": COMPOSITION,
}
LABELS = {
    "ambient_pressure": "ambient pressure",
    "ambient_oxygen_mole_fraction": "O2 mole fraction",
    "ambient_nitrogen_mole_fraction": "N2 mole fraction",
    "co2_mole_fraction": "CO2 mole fraction",
    "ambient_helium_mole_fraction": "He mole fraction",
    "initial_droplet_diameter": "initial droplet diameter",
    "extinction_diameter": "visible flame extinction diameter",
    "burning_rate_constant_mm2_s": "reported burning-rate constant K",
    "burn_time_s": "burn time",
}
FLAG_TEXT = {
    "missing_blank": "blank cell in the source",
    "missing_dash_marker": "dash marker in the source, meaning no value",
    "unparseable": "source text is not a number",
    "invalid_nonpositive_pressure": "an ambient pressure of zero or below is physically invalid",
    "negative_value_physically_implausible": "a negative value is physically implausible",
    "zero_value_meaning_unconfirmed": "the meaning of a zero value is not confirmed by the source",
    "approximate": "marked approximate in the source",
    "dext_exceeds_d0": "the extinction diameter exceeds the initial droplet diameter",
    "composition_sum_deviation": "the mole fractions do not sum to 1 within tolerance",
    "reported_K_0.05_short_translated_burn": (
        "K was reported for a short, translated burn (caveat from the NASA/TP-2015-216046 enrichment, an "
        "unregistered source)"
    ),
}


class EvidenceStatus(str, Enum):
    CLEAN = "CLEAN"
    QUALIFIED = "QUALIFIED"
    INVALID = "INVALID"
    MISSING = "MISSING"


MARKERS = {EvidenceStatus.INVALID: "FLAGGED INVALID", EvidenceStatus.QUALIFIED: "QUALIFIED"}


@dataclass(frozen=True)
class MeasurementFact:
    measurement_id: str
    run_id: str
    experiment_id: str  # FLEX-114
    psi_row: int
    source_identifier: str
    fuel: str
    variable: str  # Data Platform variable name
    label: str
    unit: str
    value: float | None  # None unless value_status is parsed/approximate (platform rule)
    original_value_text: str
    value_status: str  # parsed | approximate | missing | unparseable
    usable_for_analysis: bool  # platform rule (same function as FlexRun.usable)
    quality_flags: tuple[str, ...]
    evidence_status: EvidenceStatus
    source_column: str
    source_locator: str
    artifact_id: str
    artifact_sha256: str
    sentence: str = field(default="", compare=False)  # rendered statement, verbatim in the row chunk

    @property
    def qualifier(self) -> str:
        return "; ".join(FLAG_TEXT.get(f, f"flag {f}") for f in self.quality_flags)

    @property
    def provenance_path(self) -> str:
        return f"/api/v1/measurements/{self.measurement_id}/provenance"

    def public(self) -> dict[str, object]:
        """Tool/API view: a value is exposed only when it may be stated (CLEAN or QUALIFIED)."""
        stateable = self.evidence_status in (EvidenceStatus.CLEAN, EvidenceStatus.QUALIFIED)
        return {
            "measurement_id": self.measurement_id,
            "run_id": self.run_id,
            "variable": self.variable,
            "unit": self.unit,
            "evidence_status": self.evidence_status.value,
            "value": self.value if stateable else None,
            "value_status": self.value_status,
            "usable_for_analysis": self.usable_for_analysis,
            "quality_flags": list(self.quality_flags),
            "qualifier": self.qualifier,
            "statement": self.sentence,
            "source_column": self.source_column,
            "source_locator": self.source_locator,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "provenance": self.provenance_path,
        }


def make_locator(file_name: str, csv_line: int, source_row: int, column: str | None = None) -> str:
    """Same format as the platform's extract_flex.make_locator."""
    params: dict[str, str | int] = {"csv_line": csv_line, "flex_test": source_row}
    if column is not None:
        params["column"] = column
    return f"{file_name}#{urlencode(params, quote_via=quote)}"


def _specs() -> list[tuple[str, str, str, str]]:
    """(canonical, raw header, platform variable, unit) in the platform's column order."""
    out = [(m.canonical, m.raw_header, m.canonical, m.unit or "") for m in FLEX_COLUMNS.values()]
    out.append(("burn_time_s", BURN_TIME_HEADER, "burn_time", "s"))
    return out


def _unit_text(unit: str) -> str:
    return "mole fraction" if unit == "mole_fraction" else unit


def _status(value_status: str, usable: bool, flags: list[str]) -> EvidenceStatus:
    if value_status in ("missing", "unparseable"):
        return EvidenceStatus.MISSING
    if not usable:
        return EvidenceStatus.INVALID
    return EvidenceStatus.QUALIFIED if flags else EvidenceStatus.CLEAN


def render(f: MeasurementFact) -> str:
    unit = _unit_text(f.unit)
    head = f"{f.experiment_id} {f.label}"
    if f.evidence_status is EvidenceStatus.MISSING:
        return f"{head}: MISSING in the source ({f.qualifier}); no value exists and none is substituted."
    if f.evidence_status is EvidenceStatus.INVALID:
        return (
            f"{head}: FLAGGED INVALID ({f.qualifier}); the source cell reads '{f.original_value_text}' "
            f"{unit}, which is not usable as a measured value."
        )
    origin = (
        "reported by the FLEX team, not calculated here"
        if f.variable.startswith("burning")
        else "reported in the source"
    )
    if f.evidence_status is EvidenceStatus.QUALIFIED:
        return f"{head}: {f.original_value_text} {unit}, QUALIFIED ({f.qualifier}); {origin}."
    return f"{head}: {f.original_value_text} {unit} ({origin})."


def build_facts(runs: list[fx.FlexRun], entry: dict[str, str]) -> list[MeasurementFact]:
    sha = entry["sha256"]
    art = ids.artifact_id(sha, entry["relative_path"])
    out: list[MeasurementFact] = []
    for line_index, r in enumerate(runs):
        csv_line = line_index + 2  # line 1 is the header (same rule as the platform)
        exp = (
            f"FLEX-{r.flex_test_number:03d}" if r.flex_test_number is not None else f"PSI-69 row {r.psi_row}"
        )
        for canonical, header, variable, unit in _specs():
            flags = list(r.field_flags.get(canonical, []))
            value = r.values.get(canonical)
            if value is not None and canonical in NONNEGATIVE and value < 0:
                flags.append("negative_value_physically_implausible")
            usable = r.usable(canonical) and "negative_value_physically_implausible" not in flags
            if set(flags) & {"missing_blank", "missing_dash_marker"}:
                vstatus = "missing"
            elif "unparseable" in flags:
                vstatus = "unparseable"
            elif "approximate" in flags:
                vstatus = "approximate"
            else:
                vstatus = "parsed"
            # RAG-only qualifiers (row-level flags and known caveats); the platform keeps these on the run
            extra = [
                rf for rf, targets in ROW_FLAG_TARGETS.items() if rf in r.row_flags and canonical in targets
            ]
            if (
                canonical == "burning_rate_constant_mm2_s"
                and "reported_K_0.05_short_translated_burn" in r.sensitivity_tags
            ):
                extra.append("reported_K_0.05_short_translated_burn")
            all_flags = tuple(sorted(set(flags) | set(extra)))
            fact = MeasurementFact(
                measurement_id=ids.measurement_id(sha, r.psi_row, header),
                run_id=ids.run_id(SOURCE_ID, r.psi_row),
                experiment_id=exp,
                psi_row=r.psi_row,
                source_identifier=r.identifier,
                fuel=r.fuel,
                variable=variable,
                label=LABELS[canonical],
                unit=unit,
                value=value if vstatus in ("parsed", "approximate") else None,
                original_value_text=r.raw.get(canonical, ""),
                value_status=vstatus,
                usable_for_analysis=usable,
                quality_flags=all_flags,
                evidence_status=_status(vstatus, usable, list(all_flags)),
                source_column=header,
                source_locator=make_locator(entry["file_name"], csv_line, r.psi_row, header),
                artifact_id=art,
                artifact_sha256=sha,
            )
            out.append(_with_sentence(fact))
    return out


def _with_sentence(f: MeasurementFact) -> MeasurementFact:
    object.__setattr__(f, "sentence", render(f))
    return f
