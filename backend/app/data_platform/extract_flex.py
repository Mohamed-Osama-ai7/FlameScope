"""PSI-69 (FLEX) experimental table -> database records. Pure: reads files, never writes, no DB.

Parsing is delegated to ``app.analysis.flex_run_level`` (parse_table, verify_artifact, attach_enrichment)
so the database and the published analysis interpret every cell identically. This module adds the
relational shape: one ``experimental_runs`` row per table row and one ``measurements`` row per numeric
source cell, each with the verbatim source text, raw header, CSV line and quality flags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode

from app.analysis import flex_run_level as flex
from app.data_platform import ids
from app.data_platform.models import (
    CheckOutcome,
    CheckSeverity,
    MeasurementRole,
    ValueOrigin,
    ValueStatus,
)
from app.data_platform.vocabulary import dimension_of_variable, unit_specs
from app.domain.eligibility import explicit_exclusion
from app.domain.flex_schema import FLEX_COLUMNS, NASA_TP_FLEX
from app.domain.regimes import CombustionRegime
from app.domain.sources import SourceRecord

EXTRACTOR_NAME = "psi69_flex_experimental_table"
EXTRACTOR_VERSION = "1.0.0"
SOURCE_ID = flex.SOURCE_ID
ENRICHMENT_RELPATH = "data/derived/flex_enrichment_v1.csv"
TEXT_ENCODING = "cp1252"  # verified encoding of the PSI-69 export (en dash = 0x96)

# canonical field -> (platform variable, unit, role). Units for FLEX_COLUMNS come from flex_schema.
_ROLES: dict[str, MeasurementRole] = {
    "ambient_pressure": MeasurementRole.CONDITION,
    "ambient_oxygen_mole_fraction": MeasurementRole.CONDITION,
    "ambient_nitrogen_mole_fraction": MeasurementRole.CONDITION,
    "co2_mole_fraction": MeasurementRole.CONDITION,
    "ambient_helium_mole_fraction": MeasurementRole.CONDITION,
    "initial_droplet_diameter": MeasurementRole.CONDITION,
    "extinction_diameter": MeasurementRole.OUTCOME,
    "burning_rate_constant_mm2_s": MeasurementRole.OUTCOME,
    "burn_time_s": MeasurementRole.OUTCOME,
}
_BURN_TIME_HEADER = "Burn time; s"
_MOLE_FRACTIONS = set(flex.COMPOSITION)
_NONNEGATIVE = {
    "initial_droplet_diameter",
    "extinction_diameter",
    "burning_rate_constant_mm2_s",
    "burn_time_s",
}
_MISSING_FLAGS = {"missing_blank", "missing_dash_marker"}
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")


@dataclass(frozen=True)
class ColumnSpec:
    canonical: str
    raw_header: str
    variable: str
    unit: str
    role: MeasurementRole
    original_unit_label: str | None
    unit_evidence: str


def column_specs() -> list[ColumnSpec]:
    specs = [
        ColumnSpec(
            canonical=m.canonical,
            raw_header=m.raw_header,
            variable=m.canonical,
            unit=m.unit or "",
            role=_ROLES[m.canonical],
            original_unit_label=_header_unit(m.raw_header),
            unit_evidence=m.evidence,
        )
        for m in FLEX_COLUMNS.values()
    ]
    specs.append(
        ColumnSpec(
            canonical="burn_time_s",
            raw_header=_BURN_TIME_HEADER,
            variable="burn_time",
            unit="s",
            role=MeasurementRole.OUTCOME,
            original_unit_label="s",
            unit_evidence="Unit as labelled in the PSI-69 header 'Burn time; s'.",
        )
    )
    return specs


def _header_unit(header: str) -> str | None:
    return header.split(";", 1)[1].strip() if ";" in header else None


def make_locator(file_name: str, csv_line: int, source_row: int, column: str | None = None) -> str:
    """``<file>#csv_line=N&flex_test=M[&column=<url-encoded raw header>]``.

    Raw headers contain ';' and spaces, so the fragment is URL-encoded (RFC 3986) to stay unambiguous.
    """
    params: dict[str, str | int] = {"csv_line": csv_line, "flex_test": source_row}
    if column is not None:
        params["column"] = column
    return f"{file_name}#{urlencode(params, quote_via=quote)}"


def parse_locator(locator: str) -> dict[str, str]:
    """Inverse of make_locator: {'file': ..., 'csv_line': ..., 'flex_test': ..., 'column'?: ...}."""
    file_name, _, fragment = locator.partition("#")
    parsed = {k: v[0] for k, v in parse_qs(fragment, keep_blank_values=True, strict_parsing=True).items()}
    return {"file": file_name, **parsed}


@dataclass
class QualityCheckResult:
    check_name: str
    severity: CheckSeverity
    outcome: CheckOutcome
    affected_count: int
    description: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity is CheckSeverity.ERROR and self.outcome is CheckOutcome.FAIL


@dataclass
class ExtractionBundle:
    investigation: dict[str, Any]
    artifact: dict[str, Any]
    extraction_run: dict[str, Any]
    runs: list[dict[str, Any]]
    measurements: list[dict[str, Any]]
    checks: list[QualityCheckResult]

    @property
    def blocking_failures(self) -> list[QualityCheckResult]:
        return [c for c in self.checks if c.blocking]


class ExtractionRefused(RuntimeError):
    """Raised before anything is written when the source must not be loaded."""

    def __init__(self, message: str, checks: list[QualityCheckResult] | None = None) -> None:
        super().__init__(message)
        self.checks = checks or []


def parse_test_date(raw: str) -> tuple[date | None, list[str]]:
    """PSI-69 dates are M/D/YYYY with 50 rows using 2-digit years (variable_dictionary.csv)."""
    m = _DATE.match(raw.strip())
    if not m:
        return None, (["missing_test_date"] if not raw.strip() else ["unparseable_test_date"])
    month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
    flags: list[str] = []
    if len(year) == 2:
        flags.append("test_date_two_digit_year_assumed_20yy")
        year_int = 2000 + int(year)
    else:
        year_int = int(year)
    try:
        return date(year_int, month, day), flags
    except ValueError:
        return None, ["unparseable_test_date"]


def _value_status(flags: list[str]) -> ValueStatus:
    if set(flags) & _MISSING_FLAGS:
        return ValueStatus.MISSING
    if "unparseable" in flags:
        return ValueStatus.UNPARSEABLE
    if "approximate" in flags:
        return ValueStatus.APPROXIMATE
    return ValueStatus.PARSED


def _manifest_row(manifest: Path, source: SourceRecord) -> dict[str, str]:
    try:
        entry = flex.manifest_entry(manifest, source.source_id)
    except flex.IntegrityError as exc:
        raise ExtractionRefused(str(exc)) from exc
    if entry["relative_path"] != source.raw_file_path or entry["sha256"] != source.sha256:
        raise ExtractionRefused(
            f"{source.source_id}: source_registry.csv and artifact_manifest.csv disagree on the raw file "
            f"(registry {source.raw_file_path} {source.sha256[:12]}, manifest {entry['relative_path']} "
            f"{entry['sha256'][:12]})"
        )
    return entry


def extract(
    root: Path, source: SourceRecord, manifest: Path, code_revision: str | None = None
) -> ExtractionBundle:
    """Build all records for PSI-69. Raises ExtractionRefused on any integrity problem."""
    if source.source_id != SOURCE_ID:
        raise ExtractionRefused(
            f"extractor {EXTRACTOR_NAME} only handles {SOURCE_ID}, got {source.source_id}"
        )
    if not source.usable_as_evidence:
        raise ExtractionRefused(
            f"{source.source_id} has registry status {source.verification_status.value}; only "
            "ACQUIRED/VERIFIED sources are loaded"
        )
    excluded = explicit_exclusion(root, source.source_id)
    if excluded:
        raise ExtractionRefused(f"{source.source_id} is {excluded} (source_eligibility.csv); not loaded")
    entry = _manifest_row(manifest, source)
    raw_path = root / entry["relative_path"]
    if not raw_path.is_file():
        raise ExtractionRefused(
            f"raw file missing: {entry['relative_path']} (run: python backend/scripts/fetch_psi_table.py "
            f"{SOURCE_ID} --root .)"
        )
    raw_bytes = raw_path.read_bytes()  # read-only
    try:
        flex.verify_artifact(raw_bytes, entry)
        runs = flex.parse_table(raw_bytes)
    except flex.IntegrityError as exc:
        raise ExtractionRefused(str(exc)) from exc

    enrichment_path = root / ENRICHMENT_RELPATH
    try:
        enrichment_sha = flex.attach_enrichment(runs, enrichment_path)
    except (flex.IntegrityError, FileNotFoundError, KeyError, ValueError) as exc:
        raise ExtractionRefused(f"enrichment {ENRICHMENT_RELPATH} unusable: {exc}") from exc

    sha = entry["sha256"]
    artifact_uuid = ids.artifact_id(sha, entry["relative_path"])
    extraction_uuid = ids.extraction_run_id(EXTRACTOR_NAME, EXTRACTOR_VERSION, [sha, enrichment_sha])
    method = f"{EXTRACTOR_NAME} v{EXTRACTOR_VERSION} (parser: app.analysis.flex_run_level.parse_table)"
    specs = column_specs()

    run_rows: list[dict[str, Any]] = []
    measurement_rows: list[dict[str, Any]] = []
    for line_index, r in enumerate(runs):
        csv_line = line_index + 2  # line 1 is the header
        test_date, date_flags = parse_test_date(r.test_date)
        run_key = ids.run_id(SOURCE_ID, r.psi_row)
        run_rows.append(
            {
                "run_id": run_key,
                "investigation_id": SOURCE_ID,
                "artifact_id": artifact_uuid,
                "extraction_run_id": extraction_uuid,
                "source_row": r.psi_row,
                "source_identifier": r.identifier,
                "source_record_key": r.record_key or None,
                "combustion_regime": CombustionRegime.FLEX_DROPLET.value,
                "material_or_fuel": r.fuel or None,
                "test_date": test_date,
                "test_date_raw": r.test_date,
                "test_time_gmt_raw": r.test_time_gmt,
                "end_mode": r.test_end or None,
                "apparatus": None,
                "gravity_level_g": None,
                "source_locator": make_locator(entry["file_name"], csv_line, r.psi_row),
                "extraction_method": method,
                "quality_flags": sorted(set(r.row_flags) | set(date_flags)),
                "derived_attributes": {
                    "derived_by": "app.analysis.flex_run_level.annotate/attach_enrichment (analysis v0.2.0)",
                    "diluent_family": r.diluent_family,
                    "pressure_cluster": r.pressure_cluster,
                    "composition_sum": r.composition_sum,
                    "support_mode": r.support_mode,
                    "support_mode_provenance": (
                        "NASA/TP-2015-216046 captions (UNREGISTERED); exploration label only, "
                        "not evidence or an analysis input"
                    ),
                    "flex_test_number": r.flex_test_number,
                    "sensitivity_tags": list(r.sensitivity_tags),
                    "nasa_tp_table_ix_match": r.enrichment.get("match_method"),
                    "enrichment_verification_status": r.enrichment.get("verification_status"),
                },
            }
        )
        for spec in specs:
            raw_text = r.raw.get(spec.canonical, "")
            flags = list(r.field_flags.get(spec.canonical, []))
            value = r.values.get(spec.canonical)
            if value is not None and spec.canonical in _NONNEGATIVE and value < 0:
                flags.append("negative_value_physically_implausible")
            attributes: dict[str, Any] = {}
            if spec.canonical == "extinction_diameter":
                attributes["dext_origin"] = r.dext_origin
            status = _value_status(flags)
            measurement_rows.append(
                {
                    "measurement_id": ids.measurement_id(sha, r.psi_row, spec.raw_header),
                    "run_id": run_key,
                    "artifact_id": artifact_uuid,
                    "extraction_run_id": extraction_uuid,
                    "variable_name": spec.variable,
                    "role": spec.role.value,
                    "value": value if status in (ValueStatus.PARSED, ValueStatus.APPROXIMATE) else None,
                    "value_status": status.value,
                    "original_value_text": raw_text,
                    "unit": spec.unit,
                    "original_unit_label": spec.original_unit_label,
                    "unit_evidence": spec.unit_evidence,
                    "measured_or_derived": ValueOrigin.REPORT_VALUE.value,
                    "sensor_or_method": None,
                    "source_row": r.psi_row,
                    "source_column": spec.raw_header,
                    "source_locator": make_locator(entry["file_name"], csv_line, r.psi_row, spec.raw_header),
                    "extraction_method": method,
                    "usable_for_analysis": r.usable(spec.canonical)
                    and "negative_value_physically_implausible" not in flags,
                    "quality_flags": sorted(set(flags)),
                    "attributes": attributes,
                }
            )

    checks = run_quality_checks(runs, run_rows, measurement_rows, specs)
    now = datetime.now(UTC)
    bundle = ExtractionBundle(
        investigation={
            "investigation_id": SOURCE_ID,
            "title": source.source_title,
            "acronym": "FLEX",
            "combustion_regime": CombustionRegime.FLEX_DROPLET.value,
            "source_repository": "NASA Physical Sciences Informatics (PSI)",
            "source_url": source.source_url,
            "doi": source.doi or None,
            "license_id": source.license or None,
            "research_area": "Combustion Science",
            "official_challenge_resource": source.official_challenge_resource,
            "registry_status": source.verification_status.value,
            "metadata_json": {
                "research_area_evidence": (
                    "PSI API researchArea field, checked 2026-11-13 (see source_registry.csv)"
                ),
                "reference_report": NASA_TP_FLEX,
                "registry_version_or_release": source.version_or_release,
            },
        },
        artifact={
            "artifact_id": artifact_uuid,
            "investigation_id": SOURCE_ID,
            "artifact_kind": entry["artifact_kind"],
            "file_name": entry["file_name"],
            "relative_path": entry["relative_path"],
            "media_type": "text/csv",
            "text_encoding": TEXT_ENCODING,
            "byte_size": int(entry["byte_size"]),
            "sha256": sha,
            "source_url": entry["source_url"],
            "source_version": (
                f"PSI file version {entry['psi_file_version']}; s3 {entry['psi_s3_version_id']}"
            ),
            "license_id": entry["license"] or None,
            "retrieved_at": datetime.strptime(entry["retrieved_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            ),
            "metadata_json": {"expected_byte_size": int(entry["expected_byte_size"] or 0)},
        },
        extraction_run={
            "extraction_run_id": extraction_uuid,
            "artifact_id": artifact_uuid,
            "extractor_name": EXTRACTOR_NAME,
            "extractor_version": EXTRACTOR_VERSION,
            "inputs_json": {
                "raw": {"relative_path": entry["relative_path"], "sha256": sha},
                "enrichment": {"relative_path": ENRICHMENT_RELPATH, "sha256": enrichment_sha},
            },
            "parameters_json": {"text_encoding": TEXT_ENCODING, "two_digit_year_rule": "20YY"},
            "code_revision": code_revision,
            "run_count": len(run_rows),
            "measurement_count": len(measurement_rows),
            "first_loaded_at": now,
            "last_loaded_at": now,
        },
        runs=run_rows,
        measurements=measurement_rows,
        checks=checks,
    )
    if bundle.blocking_failures:
        names = ", ".join(c.check_name for c in bundle.blocking_failures)
        raise ExtractionRefused(f"blocking data-quality checks failed: {names}", checks)
    return bundle


# ------------------------------------------------------------------ data-quality validation


def run_quality_checks(
    runs: list[flex.FlexRun],
    run_rows: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    specs: list[ColumnSpec],
) -> list[QualityCheckResult]:
    """Structural problems are ERROR (load refused). Scientific anomalies are WARNING (kept + flagged)."""
    checks: list[QualityCheckResult] = []

    def add(name: str, severity: CheckSeverity, bad: list[Any], description: str, **details: Any) -> None:
        if severity is CheckSeverity.INFO:
            outcome = CheckOutcome.PASS
        elif bad:
            outcome = CheckOutcome.FAIL if severity is CheckSeverity.ERROR else CheckOutcome.FLAGGED
        else:
            outcome = CheckOutcome.PASS
        checks.append(QualityCheckResult(name, severity, outcome, len(bad), description, details))

    # ---- structural (ERROR) ----
    rows = [r.psi_row for r in runs]
    out_of_sequence = [row for i, row in enumerate(rows) if row != i + 1]
    add(
        "source_row_sequence",
        CheckSeverity.ERROR,
        out_of_sequence,
        "'FLEX Test #' must equal the data-line order (1..n) so row locators are unambiguous.",
        examples=out_of_sequence[:10],
    )
    run_ids = [r["run_id"] for r in run_rows]
    dup_runs = sorted({x for x in run_ids if run_ids.count(x) > 1})
    add("run_id_unique", CheckSeverity.ERROR, dup_runs, "Run keys must be unique.", examples=dup_runs[:10])
    cell_keys = [m["measurement_id"] for m in measurements]
    add(
        "measurement_cell_unique",
        CheckSeverity.ERROR,
        [] if len(cell_keys) == len(set(cell_keys)) else ["duplicate"],
        "Exactly one measurement per (artifact, row, column).",
    )
    units = unit_specs()
    bad_units = [s.raw_header for s in specs if s.unit not in units]
    add("unit_in_vocabulary", CheckSeverity.ERROR, bad_units, "Every unit must exist in the units table.")
    bad_dims = [
        s.raw_header for s in specs if s.unit in units and dimension_of_variable(s.variable) != units[s.unit]
    ]
    unknown_vars = [s.variable for s in specs if dimension_of_variable(s.variable) is None]
    add("variable_in_vocabulary", CheckSeverity.ERROR, unknown_vars, "Every variable must be defined.")
    add(
        "unit_dimension_matches_variable",
        CheckSeverity.ERROR,
        bad_dims,
        "The unit's physical dimension must equal the variable's dimension (no silent unit mix-ups).",
    )
    out_of_range = [
        f"{m['run_id']}:{m['variable_name']}={m['value']}"
        for m in measurements
        if m["variable_name"] in _MOLE_FRACTIONS and m["value"] is not None and not 0.0 <= m["value"] <= 1.0
    ]
    add(
        "mole_fraction_within_0_1",
        CheckSeverity.ERROR,
        out_of_range,
        "Mole fractions outside [0, 1] indicate a unit or column-mapping error (e.g. percent).",
        examples=out_of_range[:10],
    )
    text_mismatch = [
        m["measurement_id"]
        for m in measurements
        if m["value_status"] == ValueStatus.PARSED.value and m["original_value_text"].strip() == ""
    ]
    add(
        "original_text_preserved",
        CheckSeverity.ERROR,
        text_mismatch,
        "Every parsed value must keep its non-empty original source text.",
    )

    # ---- scientific anomalies (WARNING: kept, flagged) ----
    def flagged(flag: str, scope: str = "measurement") -> list[str]:
        if scope == "run":
            return [r["run_id"] for r in run_rows if flag in r["quality_flags"]]
        return [f"{m['run_id']}:{m['variable_name']}" for m in measurements if flag in m["quality_flags"]]

    missing_by_var: dict[str, int] = {}
    for m in measurements:
        if m["value_status"] == ValueStatus.MISSING.value:
            missing_by_var[m["variable_name"]] = missing_by_var.get(m["variable_name"], 0) + 1
    add(
        "missing_values",
        CheckSeverity.WARNING,
        [m for m in measurements if m["value_status"] == ValueStatus.MISSING.value],
        "Blank or en-dash cells. Stored with value NULL and the original marker; never converted to 0.",
        by_variable=dict(sorted(missing_by_var.items())),
    )
    for flag, scope, description in (
        ("approximate", "measurement", "Values written as '~x'; kept numeric with value_status=approximate."),
        ("unparseable", "measurement", "Non-numeric text; value NULL, text kept."),
        ("invalid_nonpositive_pressure", "measurement", "Pressure <= 0 mmHg is physically implausible."),
        ("zero_value_meaning_unconfirmed", "measurement", "Extinction diameter 0: meaning not confirmed."),
        ("negative_value_physically_implausible", "measurement", "Negative length, K or time."),
        ("duplicate_source_identifier", "run", "Same FLEX Identifier on several rows (upstream issue)."),
        ("composition_sum_deviation", "run", "O2+N2+CO2+He deviates from 1 by more than 0.02."),
        ("dext_exceeds_d0", "run", "Extinction diameter larger than initial diameter."),
        ("missing_test_time_gmt", "run", "Blank test time."),
        ("unexpected_fuel", "run", "Fuel is neither Methanol nor Heptane."),
        ("test_date_two_digit_year_assumed_20yy", "run", "2-digit year interpreted as 20YY."),
        ("unparseable_test_date", "run", "Test date could not be parsed."),
    ):
        hits = flagged(flag, scope)
        add(f"flag:{flag}", CheckSeverity.WARNING, hits, description, examples=hits[:10])

    # ---- descriptive (INFO) ----
    def counts(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in run_rows:
            out[str(r[key])] = out.get(str(r[key]), 0) + 1
        return dict(sorted(out.items()))

    add("run_count", CheckSeverity.INFO, [], "Rows loaded from the source table.", runs=len(run_rows))
    add("measurement_count", CheckSeverity.INFO, [], "Source cells loaded.", measurements=len(measurements))
    add(
        "end_mode_distribution",
        CheckSeverity.INFO,
        [],
        "Runs per 'Test end' value.",
        counts=counts("end_mode"),
    )
    add("fuel_distribution", CheckSeverity.INFO, [], "Runs per fuel.", counts=counts("material_or_fuel"))
    usable = sum(1 for m in measurements if m["usable_for_analysis"])
    add(
        "usable_for_analysis",
        CheckSeverity.INFO,
        [],
        "Measurements usable for analysis (same rule as app.analysis.flex_run_level.FlexRun.usable).",
        usable=usable,
        not_usable=len(measurements) - usable,
    )
    return checks
