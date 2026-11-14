"""Run the FLEX (PSI-69) run-level exploratory analysis and write reproducible outputs.

Usage (from repository root):
    python backend/scripts/run_flex_analysis.py

Reads data/raw/PSI-69/... (verified against data/metadata/artifact_manifest.csv) plus the
provenance-linked enrichment data/derived/flex_enrichment_v1.csv, and writes to
reports/flex_run_level_v0.2/. The approved v0.1.0 outputs in reports/flex_run_level/ are left
untouched. Output is deterministic (no timestamps) so reruns are diff-able.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.analysis import flex_run_level as fx  # noqa: E402
from app.analysis.svg_charts import Point, scatter_by_fuel  # noqa: E402
from app.domain.eligibility import EligibilityPolicy  # noqa: E402

ANALYSIS_VERSION = "0.2.0"
ENRICHMENT = Path("data") / "derived" / "flex_enrichment_v1.csv"
FOOT = (
    "Source: NASA PSI-69 (FLEX), DOI 10.60555/mbq8-0451, CC0. NASA-reported values; descriptive and "
    "observational only - no causal claim, not a safety limit. Hover a point for its record."
)


def tier_labels(runs: list[fx.FlexRun]) -> dict[str, str]:
    """Collapse pressure clusters into <= 3 chart tiers (lowest, next, all higher)."""
    lo_of = {r.pressure_cluster: r.pressure_cluster_lo for r in runs if r.pressure_cluster}
    clusters = sorted(lo_of, key=lambda c: lo_of[c] or 0.0)
    out = {}
    for i, c in enumerate(clusters):
        if i < 2:
            out[c] = c
        else:
            out[c] = f">= {min(lo_of[x] or 0.0 for x in clusters[2:]):g} mmHg ({len(clusters) - 2} clusters)"
    return out


def tip(r: fx.FlexRun) -> str:
    v = r.values
    return (
        f"{r.record_key or r.psi_row} | {r.support_mode} | {r.fuel} | "
        f"X_O2={v['ambient_oxygen_mole_fraction']} "
        f"X_CO2={v['co2_mole_fraction']} X_He={v['ambient_helium_mole_fraction']} | "
        f"P={v['ambient_pressure']} mmHg | D0={v['initial_droplet_diameter']} mm | "
        f"K={v['burning_rate_constant_mm2_s']} mm2/s | Dext={v['extinction_diameter']} | {r.test_end}"
    )


def panels(runs, select, xvar, yvar, group_of):
    out = {}
    for fuel in fx.FUELS:
        pts = []
        for r in runs:
            if r.fuel != fuel or not select(r) or not (r.usable(xvar) and r.usable(yvar)):
                continue
            g = group_of(r)
            if g is None:
                continue
            pts.append(Point(r.values[xvar], r.values[yvar], g, tip(r)))
        out[fuel] = pts
    return out


def make_charts(runs: list[fx.FlexRun], outdir: Path, by_support: bool = True) -> list[dict[str, Any]]:
    """by_support=False (v0.3.0): no free-floating filter; support mode is never an analysis input."""
    """Primary charts show FREE-FLOATING droplets only (fiber-supported runs are a different flow regime)."""
    outdir.mkdir(parents=True, exist_ok=True)
    tiers = tier_labels(runs)
    tier_order = list(dict.fromkeys(tiers.values()))

    def by_tier(r):
        return tiers.get(r.pressure_cluster) if r.pressure_cluster else None

    K, O2 = "burning_rate_constant_mm2_s", "ambient_oxygen_mole_fraction"
    comp_ok = lambda r: all(r.usable(c) for c in fx.COMPOSITION) and r.usable("ambient_pressure")  # noqa: E731
    specs = [
        (
            "fig1_K_vs_O2_N2only.svg",
            "Reported burning-rate constant vs O2 (N2-only atmospheres)",
            "O2 is the single free composition variable when N2 is the only balance gas. "
            "Colour = pressure cluster.",
            O2,
            K,
            "O2 mole fraction",
            "Reported K (mm2/s)",
            lambda r: comp_ok(r) and r.diluent_family == "N2_only",
            by_tier,
            tier_order,
        ),
        (
            "fig2_K_vs_CO2.svg",
            "Reported burning-rate constant vs CO2 (CO2-added atmospheres)",
            "O2 also varies between runs here; see fixed-O2 strata in the summary. "
            "Colour = pressure cluster.",
            "co2_mole_fraction",
            K,
            "CO2 mole fraction",
            "Reported K (mm2/s)",
            lambda r: comp_ok(r) and r.diluent_family == "CO2_added",
            by_tier,
            tier_order,
        ),
        (
            "fig3_K_vs_He.svg",
            "Reported burning-rate constant vs He (He-added atmospheres)",
            "O2 also varies between runs here; see fixed-O2 strata in the summary. "
            "Colour = pressure cluster.",
            "ambient_helium_mole_fraction",
            K,
            "He mole fraction",
            "Reported K (mm2/s)",
            lambda r: comp_ok(r) and r.diluent_family == "He_added",
            by_tier,
            tier_order,
        ),
        (
            "fig4_K_vs_pressure_N2only.svg",
            "Reported burning-rate constant vs ambient pressure (N2-only)",
            "Colour separates the air-like O2 = 0.21 runs from other O2 levels.",
            "ambient_pressure",
            K,
            "Ambient pressure (mmHg)",
            "Reported K (mm2/s)",
            lambda r: comp_ok(r) and r.diluent_family == "N2_only",
            lambda r: "O2 = 0.21" if r.values[O2] == 0.21 else "O2 other",
            ["O2 = 0.21", "O2 other"],
        ),
        (
            "fig5_K_vs_D0.svg",
            "Reported burning-rate constant vs initial droplet diameter",
            "Colour = diluent family. O2 and pressure also vary within each colour (confounded).",
            "initial_droplet_diameter",
            K,
            "Initial droplet diameter D0 (mm)",
            "Reported K (mm2/s)",
            comp_ok,
            lambda r: r.diluent_family if r.diluent_family in ("N2_only", "CO2_added", "He_added") else None,
            ["N2_only", "CO2_added", "He_added"],
        ),
        (
            "fig6_Dext_vs_O2_N2only.svg",
            "Visible flame extinction diameter vs O2 (N2-only, extinction runs)",
            "Eligible: test end = Extinction, positive diameter, no extrapolation noted in the caption. "
            "D0 also varies. Colour = pressure cluster.",
            O2,
            "extinction_diameter",
            "O2 mole fraction",
            "Extinction diameter (mm)",
            lambda r: (
                comp_ok(r)
                and r.diluent_family == "N2_only"
                and r.dext_origin == "reported_extinction_no_extrapolation_noted"
            ),
            by_tier,
            tier_order,
        ),
        (
            "fig7_outcome_by_O2_D0_N2only.svg",
            "Test outcome by O2 and initial diameter (N2-only)",
            "Colour/shape = how the test ended. Outcome categories are as reported by NASA.",
            O2,
            "initial_droplet_diameter",
            "O2 mole fraction",
            "Initial droplet diameter D0 (mm)",
            lambda r: comp_ok(r) and r.diluent_family == "N2_only",
            lambda r: r.test_end,
            ["Extinction", "Disruption", "Completion"],
        ),
    ]
    made = []
    for fname, title, sub, xv, yv, xl, yl, sel, grp, order in specs:
        keep = (lambda r: r.support_mode == "free_floating") if by_support else (lambda r: True)
        p = panels(runs, lambda r, sel=sel, keep=keep: sel(r) and keep(r), xv, yv, grp)
        other = {
            f: sum(
                1 for r in runs if r.fuel == f and sel(r) and not keep(r) and r.usable(xv) and r.usable(yv)
            )
            for f in fx.FUELS
        }
        used = [g for g in order if any(pt.group == g for pts in p.values() for pt in pts)]
        sub = (
            f"{sub} Free-floating droplets only; not shown: fiber/unknown-support runs "
            f"(methanol {other['Methanol']}, heptane {other['Heptane']})."
            if by_support
            else f"{sub} All support modes pooled (support mode not controlled; its only source is the "
            "unregistered NASA/TP-2015-216046)."
        )
        svg = scatter_by_fuel(title, sub, xl, yl, p, used, FOOT)
        (outdir / fname).write_text(svg, encoding="utf-8", newline="\n")
        made.append(
            {
                "file": fname,
                "title": title,
                "n_by_fuel": {f: len(v) for f, v in p.items()},
                "not_shown_non_free_floating": other,
                "groups": used,
                "plotted_record_keys": {
                    f: sorted(pt.tooltip.split(" | ")[0] for pt in v) for f, v in p.items()
                },
            }
        )
    return made


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--enrichment", type=Path, default=None)
    ap.add_argument(
        "--no-support-mode",
        action="store_true",
        help="analysis v0.3.0: support modes (unregistered NASA/TP captions) are not an analysis input",
    )
    args = ap.parse_args(argv)
    root: Path = args.root
    by_support = not args.no_support_mode
    version = ANALYSIS_VERSION if by_support else "0.3.0"
    out: Path = args.out or root / "reports" / f"flex_run_level_v{version.rsplit('.', 1)[0]}"
    manifest = root / "data" / "metadata" / "artifact_manifest.csv"
    entry = fx.manifest_entry(manifest)
    runs, entry = fx.load_verified(root / entry["relative_path"], manifest)
    enrichment_path = args.enrichment or root / ENRICHMENT
    enrichment_sha = fx.attach_enrichment(runs, enrichment_path)

    results = fx.run_analyses(runs, stratify_by_support_mode=by_support)
    quality = fx.quality_report(runs)
    desc = fx.descriptive_by_fuel(runs)
    out.mkdir(parents=True, exist_ok=True)
    charts = make_charts(runs, out / "charts", by_support)

    summary = {
        "analysis": "FLEX run-level exploratory analysis",
        "analysis_version": version,
        "source": {
            "source_id": fx.SOURCE_ID,
            "doi": "10.60555/mbq8-0451",
            "file_name": entry["file_name"],
            "source_url": entry["source_url"],
            "psi_file_version": entry["psi_file_version"],
            "psi_s3_version_id": entry["psi_s3_version_id"],
            "sha256": entry["sha256"],
            "sha256_verified_before_analysis": True,
            "byte_size": int(entry["byte_size"]),
            "license": entry["license"],
            "retrieved_at_utc": entry["retrieved_at_utc"],
            "schema_reference": "NASA/TP-2015-216046 Appendix A.1 and Table IX "
            "(https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf)",
        },
        "scope": {
            "psi_rows_analysed": len(runs),
            "nasa_report_states_tests": 284,
            "note": "274 PSI rows are not the 284 tests stated by NASA/TP-2015-216046; difference "
            "unresolved (see data/metadata/flex_report_reconciliation.json). Results describe "
            "the 274 PSI rows only.",
        },
        "enrichment": {
            "file": ENRICHMENT.as_posix(),
            "sha256": enrichment_sha,
            "built_by": "backend/scripts/build_flex_enrichment.py from NASA/TP-2015-216046 "
            "(PDF sha256 b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d)",
        },
        "supersedes_interpretation_of": "v0.1.0 (reports/flex_run_level/, outputs kept unchanged); "
        "see docs/11",
        "value_origin": "reported_in_source (burning_rate_constant_mm2_s); d2-law calculator NOT used",
        "multiple_comparisons": {
            "strata_total": len(results["strata"]),
            "strata_with_rho": sum(1 for s in results["strata"] if s["rho_spearman"] is not None),
            "statement": "Many strata were examined; no correction for multiple comparisons is applied "
            "and no coefficient is a test of significance. All strata are reported, none selected.",
        },
        "analysis_choices": {
            "pressure_cluster_gap_mmHg": fx.PRESSURE_CLUSTER_GAP_MMHG,
            "composition_sum_tolerance_report_only": fx.COMPOSITION_SUM_TOLERANCE,
            "min_n_for_spearman": fx.MIN_N_FOR_RANK_CORRELATION,
            "min_n_meaning": "reporting floor only; n >= 5 is not evidence of reliability",
            "pressure_cluster_justification": "clusters identical for gap rules 25-200 mmHg and labelled "
            "by NASA nominal design levels 0.70/1.00/2.03/2.72/3.05 atm",
            "support_mode_stratification": (
                "every K and Dext stratum is split by support mode "
                "(free-floating, fiber translated, fiber translation not stated, conflicting sources)"
                if by_support
                else "NOT used: support modes come only from NASA/TP-2015-216046 captions (unregistered); "
                "strata pool support modes and are labelled support_mode='not_controlled', so support "
                "mode is an uncontrolled confounder in every K and Dext stratum"
            ),
            "sensitivity_rows": list(fx.SENSITIVITY_TAGS),
            "statistic": "Spearman rank correlation (descriptive; no p-values, no regression, no prediction)",
            "compositional_rule": "O2 only within N2-only runs; CO2/He only at fixed O2 (with N2-only "
            "zero-diluent runs at the same O2 and pressure cluster as reference)",
        },
        "quality": {k: v for k, v in quality.items() if k != "flagged_rows"},
        "descriptive_by_fuel": desc,
        "reported_K_by_fuel_and_support_mode": "not computed in v0.3.0 (support mode is not an input)"
        if not by_support
        else {
            f: {
                sm: fx.describe(
                    fx._vals(
                        [r for r in runs if r.fuel == f and r.support_mode == sm],
                        "burning_rate_constant_mm2_s",
                    )
                )
                for sm in sorted({r.support_mode for r in runs if r.fuel == f})
            }
            for f in fx.FUELS
        },
        "sensitivity_reported_K_0.05_FLEX_130": {
            "primary_retains_source_value": True,
            "heptane_K_all_rows": desc["Heptane"]["K_reported_mm2_s"],
            "heptane_K_without_FLEX_130": fx.describe(
                fx._vals(
                    [r for r in runs if r.fuel == "Heptane" and r.flex_test_number != 130],
                    "burning_rate_constant_mm2_s",
                )
            ),
            "context": "Table IX value confirmed visually; caption: fiber-supported, translating 3 mm/s, "
            "very short burn, radiative extinction soon after translation began (burn time 0.6 s).",
        },
        "results": results,
        "charts": charts,
    }
    if not by_support:  # v0.3.0 only (v0.2.0 outputs stay byte-identical)
        summary["evidence_eligibility"] = {
            fx.SOURCE_ID: EligibilityPolicy(root).decision(fx.SOURCE_ID).eligibility.value
        }
        summary["unregistered_inputs_remaining"] = (
            "A6 (extinction diameter) eligibility still uses dext_origin, which reads caption "
            "extrapolation notes from NASA/TP-2015-216046 (unregistered); FLEX test numbers come from the "
            "approved Table IX cross-match. See docs/22."
        )
    # newline="\n": identical bytes on every OS (these hashes are pinned in tests and in the lab dataset)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    (out / "quality_report.json").write_text(
        json.dumps(quality, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    write_csv(out / "row_quality_table.csv", fx.row_table(runs))
    write_csv(
        out / "descriptive_by_fuel.csv",
        [{"fuel": f, "variable": v, **stats} for f, d in desc.items() for v, stats in d.items()],
    )
    write_csv(
        out / "strata_results.csv",
        [
            {
                "analysis": s["analysis"],
                "fuel": s["fuel"],
                "stratum": json.dumps({k: v for k, v in s["stratum"].items() if k != "by_pressure_cluster"}),
                "x": s["x"],
                "y": s["y"],
                "n": s["n"],
                "rho_spearman": "" if s["rho_spearman"] is None else round(s["rho_spearman"], 3),
                "evidence_class": s["evidence_class"],
                "n_values_in_x_ties": s["n_values_in_x_ties"],
                "n_values_in_y_ties": s["n_values_in_y_ties"],
                "sensitivity_rows": " ".join(map(str, s["sensitivity_rows"])),
                "rho_without_sensitivity_rows": ""
                if s["rho_without_sensitivity_rows"] is None
                else round(s["rho_without_sensitivity_rows"], 3),
                "x_min": s["x_summary"]["min"],
                "x_max": s["x_summary"]["max"],
                "y_median": s["y_summary"]["median"],
                "note": s["note"],
                "psi_rows": " ".join(map(str, s["psi_rows"])),
            }
            for s in results["strata"]
        ],
    )
    print(f"Verified {entry['file_name']} sha256={entry['sha256']}")
    print(f"Rows analysed: {len(runs)} (by fuel: {quality['rows_by_fuel']})")
    print(f"Strata: {len(results['strata'])} | charts: {len(charts)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
