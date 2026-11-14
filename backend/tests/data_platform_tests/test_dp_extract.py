"""Extraction against the real PSI-69 bytes: provenance, fidelity, quality flags, refusals."""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

import pytest

from app.data_platform import extract_flex as ex
from app.domain.sources import SourceRecord, VerificationStatus, find_source, load_registry

from .conftest import PROJECT_ROOT, RAW_PSI69, needs_raw

REGISTRY = PROJECT_ROOT / "data" / "metadata" / "source_registry.csv"
MANIFEST = PROJECT_ROOT / "data" / "metadata" / "artifact_manifest.csv"
LAB_DATASET = PROJECT_ROOT / "frontend" / "public" / "data" / "flex_lab_dataset_v0.2.0.json"


def psi69() -> SourceRecord:
    src = find_source(load_registry(REGISTRY), "PSI-69")
    assert src is not None
    return src


@pytest.fixture(scope="module")
def bundle() -> ex.ExtractionBundle:
    if not RAW_PSI69.exists():
        pytest.skip("raw PSI-69 table not present (gitignored)")
    return ex.extract(PROJECT_ROOT, psi69(), MANIFEST)


@needs_raw
def test_shape_and_checks(bundle):
    assert len(bundle.runs) == 274
    assert len(bundle.measurements) == 274 * 9
    assert not bundle.blocking_failures
    checks = {c.check_name: c for c in bundle.checks}
    # Facts recorded independently in data/metadata/variable_dictionary.csv
    assert checks["end_mode_distribution"].details["counts"] == {
        "Completion": 27,
        "Disruption": 61,
        "Extinction": 186,
    }
    assert checks["fuel_distribution"].details["counts"] == {"Heptane": 117, "Methanol": 157}
    assert checks["flag:test_date_two_digit_year_assumed_20yy"].affected_count == 50
    assert checks["flag:missing_test_time_gmt"].affected_count == 1
    assert sorted(checks["flag:duplicate_source_identifier"].details["examples"]) == [
        "PSI-69-r070",
        "PSI-69-r073",
    ]
    assert checks["flag:approximate"].affected_count == 2
    assert checks["flag:invalid_nonpositive_pressure"].details["examples"] == ["PSI-69-r114:ambient_pressure"]


@needs_raw
def test_every_measurement_points_at_its_exact_source_cell(bundle):
    """Re-read the raw bytes independently and compare each stored cell (location + verbatim text)."""
    lines = list(csv.reader(io.StringIO(RAW_PSI69.read_bytes().decode("cp1252"))))
    header = lines[0]
    for m in bundle.measurements:
        locator = ex.parse_locator(m["source_locator"])
        assert locator["file"] == RAW_PSI69.name
        line = lines[int(locator["csv_line"]) - 1]
        assert int(line[header.index("FLEX Test #")]) == m["source_row"] == int(locator["flex_test"])
        assert locator["column"] == m["source_column"]
        assert line[header.index(m["source_column"])] == m["original_value_text"]
    for r in bundle.runs:
        assert set(ex.parse_locator(r["source_locator"])) == {"file", "csv_line", "flex_test"}


def test_locator_round_trips_headers_with_separators():
    header = "CO initial ambient composition; mole fraction"
    loc = ex.make_locator("PSI-69_Experimental table_FLEX.csv", 2, 1, header)
    assert ex.parse_locator(loc) == {
        "file": "PSI-69_Experimental table_FLEX.csv",
        "csv_line": "2",
        "flex_test": "1",
        "column": header,
    }


@needs_raw
def test_missing_is_never_zero_and_status_matches_value(bundle):
    for m in bundle.measurements:
        if m["value_status"] in ("missing", "unparseable"):
            assert m["value"] is None and not m["usable_for_analysis"]
        else:
            assert m["value"] is not None
            assert float(m["original_value_text"].lstrip("~").strip()) == m["value"]
    dash = [m for m in bundle.measurements if m["original_value_text"] == "–"]
    assert dash and all("missing_dash_marker" in m["quality_flags"] for m in dash)


@needs_raw
def test_provenance_fields_complete(bundle):
    art = bundle.artifact
    assert art["sha256"] == psi69().sha256 and art["text_encoding"] == "cp1252"
    for m in bundle.measurements:
        assert m["artifact_id"] == art["artifact_id"]
        assert m["extraction_run_id"] == bundle.extraction_run["extraction_run_id"]
        assert m["unit"] and m["variable_name"] and m["source_locator"] and m["extraction_method"]
        assert m["measured_or_derived"] == "report_value"


@needs_raw
def test_values_match_frontend_lab_dataset(bundle):
    """Integration contract with the frontend: same record_key -> same raw text and same value."""
    data = json.loads(LAB_DATASET.read_text(encoding="utf-8"))
    by_key = {r["record_key"]: r for r in data["records"]}
    runs = {r["run_id"]: r for r in bundle.runs}
    assert {r["source_record_key"] for r in bundle.runs} == set(by_key)
    field_for_variable = {s.variable: s.canonical for s in ex.column_specs()}
    for m in bundle.measurements:
        rec = by_key[runs[m["run_id"]]["source_record_key"]]
        canonical = field_for_variable[m["variable_name"]]
        assert rec["raw"][canonical] == m["original_value_text"], (m["run_id"], canonical)
        assert rec["values"][canonical] == m["value"], (m["run_id"], canonical)


@needs_raw
def test_extraction_is_deterministic():
    a = ex.extract(PROJECT_ROOT, psi69(), MANIFEST)
    b = ex.extract(PROJECT_ROOT, psi69(), MANIFEST)
    assert a.runs == b.runs and a.measurements == b.measurements


def test_quarantined_and_wrong_sources_are_refused():
    records = load_registry(REGISTRY)
    with pytest.raises(ex.ExtractionRefused, match="only handles PSI-69"):
        ex.extract(PROJECT_ROOT, find_source(records, "PSI-98"), MANIFEST)  # type: ignore[arg-type]
    quarantined = psi69().model_copy(update={"verification_status": VerificationStatus.QUARANTINED})
    with pytest.raises(ex.ExtractionRefused, match="QUARANTINED"):
        ex.extract(PROJECT_ROOT, quarantined, MANIFEST)


def _tmp_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "data" / "metadata").mkdir(parents=True)
    shutil.copy(MANIFEST, root / "data" / "metadata" / "artifact_manifest.csv")
    (root / "data" / "derived").mkdir()
    shutil.copy(PROJECT_ROOT / ex.ENRICHMENT_RELPATH, root / ex.ENRICHMENT_RELPATH)
    return root


def test_missing_raw_file_is_refused_with_fetch_hint(tmp_path):
    root = _tmp_root(tmp_path)
    with pytest.raises(ex.ExtractionRefused, match="fetch_psi_table.py"):
        ex.extract(root, psi69(), root / "data" / "metadata" / "artifact_manifest.csv")


def test_tampered_bytes_are_refused(tmp_path):
    root = _tmp_root(tmp_path)
    target = root / psi69().raw_file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"FLEX Test #,Fuel\r\n1,Heptane\r\n")  # not the registered bytes
    with pytest.raises(ex.ExtractionRefused, match="SHA-256 mismatch"):
        ex.extract(root, psi69(), root / "data" / "metadata" / "artifact_manifest.csv")


def test_registry_manifest_disagreement_is_refused():
    wrong = psi69().model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ex.ExtractionRefused, match="disagree"):
        ex.extract(PROJECT_ROOT, wrong, MANIFEST)
