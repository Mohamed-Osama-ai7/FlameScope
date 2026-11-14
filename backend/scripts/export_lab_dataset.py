"""Export the Scientific Exploration Lab dataset from the approved v0.2.0 FLEX analysis.

Usage (from repository root):
    python backend/scripts/export_lab_dataset.py

Packages, without new calculations:
* every PSI-69 record (verified SHA-256) with raw strings, canonical values, units and flags;
* the provenance-linked enrichment (support mode, FLEX number, record key, captions, conflicts);
* analysis eligibility = membership in the v0.2.0 strata produced by app.analysis.flex_run_level;
* all v0.2.0 strata statistics (Spearman rho is computed in Python only, never in the browser);
* provenance: source URL, DOI, versions, SHA-256 of raw table, enrichment and v0.2.0 summary.

Output: frontend/public/data/flex_lab_dataset_v0.2.0.json (deterministic; no timestamps).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.analysis import flex_run_level as fx  # noqa: E402

DATASET_VERSION = "lab-1"
ANALYSIS_VERSION = "0.2.0"
OUT = ROOT / "frontend" / "public" / "data" / f"flex_lab_dataset_v{ANALYSIS_VERSION}.json"
UNITS = {
    "ambient_pressure": "mmHg",
    "ambient_oxygen_mole_fraction": "mole fraction",
    "ambient_nitrogen_mole_fraction": "mole fraction",
    "co2_mole_fraction": "mole fraction",
    "ambient_helium_mole_fraction": "mole fraction",
    "initial_droplet_diameter": "mm",
    "extinction_diameter": "mm",
    "burning_rate_constant_mm2_s": "mm²/s",
    "burn_time_s": "s",
}
RAW_HEADERS = {
    "ambient_pressure": "Ambient pressure; mmHg",
    "ambient_oxygen_mole_fraction": "O initial ambient composition; mole fraction",
    "ambient_nitrogen_mole_fraction": "N initial ambient composition; mole fraction",
    "co2_mole_fraction": "CO initial ambient composition; mole fraction",
    "ambient_helium_mole_fraction": "He initial ambient composition; mole fraction",
    "initial_droplet_diameter": "Droplet initial diameter; mm",
    "extinction_diameter": "Visible flame extinction diameter; mm",
    "burning_rate_constant_mm2_s": "Burning rate; mm",
    "burn_time_s": "Burn time; s",
}
DOC = "docs/11_flex_scientific_audit.md"
RULES = {
    "eligibility.A1": "O2 vs reported K: N2-only atmospheres (CO2 = He = 0), valid pressure and composition, "
    "reported K present; stratified by fuel x pressure cluster x support mode.",
    "eligibility.A2": "CO2 vs reported K at a fixed O2 value (CO2-added runs plus N2-only zero-diluent reference "
    "runs at the same O2, pressure cluster and support mode). Confounded: N2 trades with CO2.",
    "eligibility.A3": "He vs reported K at a fixed O2 value (as A2). Confounded: N2 trades with He.",
    "eligibility.A4": "Pressure vs reported K at fixed O2 in N2-only runs spanning >= 2 pressure clusters.",
    "eligibility.A5": "D0 vs reported K within fuel x diluent family x pressure cluster x support mode. "
    "Confounded: O2 and diluent vary; unresolved (docs/11 sec. 5).",
    "eligibility.A6": "O2 vs visible flame extinction diameter: test end = Extinction, positive diameter, no "
    "extrapolation noted in the NASA caption, N2-only, valid pressure.",
    "quality.missing_blank": "Field blank in PSI/Table IX.",
    "quality.missing_dash_marker": "En dash in source. For extinction diameter, NASA App. A.1: no extinction "
    "(completion or disruption).",
    "quality.approximate": "Value prefixed '~' in source; kept as approximate.",
    "quality.invalid_nonpositive_pressure": "Absolute pressure <= 0 is not a physical ambient pressure; raw kept.",
    "quality.duplicate_source_identifier": "FLEX identifier appears on more than one record; both records kept.",
    "quality.composition_sum_deviation": "O2+N2+CO2+He differs from 1 by > 0.02 (H2O and fuel vapour are not in "
    "the table; report-only flag).",
    "quality.dext_exceeds_d0": "Extinction diameter larger than D0 (within +/-50 um droplet-size uncertainty).",
    "quality.missing_test_time_gmt": "GMT missing in source.",
    "quality.zero_value_meaning_unconfirmed": "Zero extinction diameter; meaning not defined by NASA.",
    "evidence.shutter_1_30s_period": "FLEX-001..009: 1/30 s shutter, droplet size at ignition ambiguous "
    "(NASA/TP-2015-216046 sec. 4). Labelled sensitivity, never removed.",
    "evidence.reported_K_0.05_short_translated_burn": "FLEX-130: K = 0.05 mm²/s confirmed as printed; fiber-"
    "supported, translating 3 mm/s, very short burn. Retained; labelled sensitivity.",
    "evidence.coated_needle_period": "All tests in the report used coated needles (sec. 5.2). NASA: K minimally "
    "influenced; methanol disruption probably due to contaminant; no conclusion for heptane disruption.",
    "evidence.conflicting_sources": "Support mode in caption contradicts matrix table (FLEX-053, FLEX-124).",
    "evidence.pressure_source_conflict": "Table IX/PSI pressure contradicts the matrix table (FLEX-114).",
    "evidence.unmapped_tests": "Table IX rows FLEX-216 and FLEX-230 are not in PSI-69; 284 tests stated, 276 "
    "printed, 274 in PSI (unresolved).",
    "evidence.missing_composition": "H2O and fuel-vapour mole fractions are defined in App. A.1 but absent from "
    "Table IX and PSI-69: composition is INCOMPLETE and is never normalised.",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = ROOT / "data" / "metadata" / "artifact_manifest.csv"
    entry = fx.manifest_entry(manifest)
    runs, entry = fx.load_verified(ROOT / entry["relative_path"], manifest)
    enrichment_path = ROOT / "data" / "derived" / "flex_enrichment_v1.csv"
    enrichment_sha = fx.attach_enrichment(runs, enrichment_path)
    captions_path = ROOT / "data" / "derived" / "flex_enrichment_v1_captions.json"
    captions = json.loads(captions_path.read_text(encoding="utf-8"))["captions"]
    results = fx.run_analyses(runs)
    summary_path = ROOT / "reports" / "flex_run_level_v0.2" / "summary.json"

    membership: dict[int, set[str]] = {r.psi_row: set() for r in runs}
    for s in results["strata"]:
        for n in s["psi_rows"]:
            membership[n].add(s["analysis"].split("_")[0])

    records: list[dict[str, Any]] = []
    for r in sorted(runs, key=lambda x: x.psi_row):
        e = r.enrichment
        cap = captions.get(f"FLEX-{r.flex_test_number:03d}") if r.flex_test_number else None
        records.append({
            "record_key": r.record_key,
            "psi_row": r.psi_row,
            "flex_test_number": r.flex_test_number,
            "identifier": r.identifier,
            "test_date": r.test_date,
            "test_gmt": r.test_time_gmt or None,
            "fuel": r.fuel,
            "test_end": r.test_end,
            "values": {k: r.values[k] for k in fx.NUMERIC_FIELDS},
            "raw": {k: r.raw.get(k, "") for k in fx.NUMERIC_FIELDS},
            "field_flags": {k: v for k, v in r.field_flags.items() if v},
            "row_flags": r.row_flags,
            "usable": {k: r.usable(k) for k in fx.NUMERIC_FIELDS},
            "diluent_family": r.diluent_family,
            "pressure_cluster": r.pressure_cluster,
            "composition_sum": r.composition_sum,
            "support_mode": r.support_mode,
            "support_basis": e.get("support_basis", ""),
            "dext_origin": r.dext_origin,
            "sensitivity_tags": r.sensitivity_tags,
            "eligible": sorted(membership[r.psi_row]),
            "evidence": {
                "table_ix_pdf_page": int(e["table_ix_pdf_page"]),
                "table_ix_printed_page": int(e["table_ix_printed_page"]),
                "caption_figure": int(e["caption_figure"]) if e.get("caption_figure") else None,
                "caption_pdf_page": int(e["caption_pdf_page"]) if e.get("caption_pdf_page") else None,
                "caption": cap["caption"] if cap else None,
                "matrix_table": e.get("matrix_table") or None,
                "matrix_table_fiber": e.get("matrix_table_fiber"),
                "matrix_table_pressure_atm": float(e["matrix_table_pressure_atm"])
                if e.get("matrix_table_pressure_atm") else None,
                "pressure_source_conflict": e.get("pressure_source_conflict") or None,
                "shutter_1_30s_period": e.get("shutter_1_30s_period") == "True",
                "coated_needle_period": e.get("coated_needle_period") == "True",
                "documented_contamination_or_feature": e.get("documented_contamination_or_feature") or None,
                "dext_caption_note": e.get("dext_caption_note") or None,
                "match_method": e.get("match_method"),
                "verification_status": e.get("verification_status"),
            },
        })

    strata = []
    for s in results["strata"]:
        strata.append({k: s[k] for k in ("analysis", "fuel", "x", "y", "n", "rho_spearman", "note",
                                         "n_values_in_x_ties", "n_values_in_y_ties", "sensitivity_rows",
                                         "rho_without_sensitivity_rows", "evidence_class", "psi_rows")}
                      | {"stratum": {k: v for k, v in s["stratum"].items() if k != "by_pressure_cluster"}})

    dataset = {
        "dataset": "FlameScope Scientific Exploration Lab - FLEX (PSI-69)",
        "dataset_version": DATASET_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "synthetic": False,
        "value_origin": "NASA-reported values (burning_rate_constant_mm2_s is the FLEX team's reported K, not a "
                        "FlameScope calculation; the d2-law calculator is not used).",
        "provenance": {
            "source_id": fx.SOURCE_ID,
            "doi": "10.60555/mbq8-0451",
            "license": entry["license"],
            "source_url": entry["source_url"],
            "file_name": entry["file_name"],
            "psi_file_version": entry["psi_file_version"],
            "psi_s3_version_id": entry["psi_s3_version_id"],
            "raw_sha256": entry["sha256"],
            "retrieved_at_utc": entry["retrieved_at_utc"],
            "enrichment_file": "data/derived/flex_enrichment_v1.csv",
            "enrichment_sha256": enrichment_sha,
            "captions_sha256": sha(captions_path),
            "analysis_summary_file": "reports/flex_run_level_v0.2/summary.json",
            "analysis_summary_sha256": sha(summary_path),
            "report": "NASA/TP-2015-216046 (Dietrich et al., 2015)",
            "report_url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf",
            "report_pdf_sha256": "b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d",
            "audit_doc": DOC,
        },
        "scope": {"records": len(records), "unique_flex_tests": len({r["flex_test_number"] for r in records}),
                  "unique_identifiers": len({r["identifier"] for r in records}),
                  "nasa_stated_tests": 284, "table_ix_printed_rows": 276,
                  "table_ix_rows_not_in_psi": ["FLEX-216", "FLEX-230"]},
        "units": UNITS,
        "raw_headers": RAW_HEADERS,
        "rules": RULES,
        "unknown_fields": ["H2O mole fraction", "heptane vapour mole fraction", "methanol vapour mole fraction",
                           "uncertainty of reported K"],
        "outcome_caveats": results["outcomes"]["contamination_caveats"],
        "records": records,
        "strata": strata,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(  # newline="\n": identical bytes on every OS (hash is pinned)
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"records={len(records)} strata={len(strata)} -> {OUT.relative_to(ROOT)} sha256={sha(OUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
