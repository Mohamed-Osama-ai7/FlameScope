"""FLEX (PSI-69) run-level exploratory analysis.

Scope and rules (docs/10_flex_run_level_analysis.md):

* Input is the acquired PSI-69 experimental table, verified by SHA-256 against
  data/metadata/artifact_manifest.csv before any parsing. Raw bytes are never modified.
* All 274 rows are kept. Duplicate identifiers are retained (rows are keyed by PSI row number).
* Missing ('', en dash), approximate ('~x') and invalid values are kept with explicit flags; each
  analysis records how many rows it excluded and why.
* Values are REPORTED by the FLEX team (``burning_rate_constant_mm2_s``). The d^2-law calculator is
  not used: the table has no diameter-time histories.
* Fuels are never pooled. Gas mole fractions are treated as compositional: O2 is examined only where
  N2 is the sole balance gas; CO2 and He only at a fixed O2 value.
* Statistics are descriptive (counts, quantiles, Spearman rank correlation). No regression, ML,
  prediction, p-values or causal claims.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.domain.comparison import (
    ComparisonClass,
    Condition,
    ObservationDescriptor,
    validate_comparison,
)
from app.domain.flex_schema import FLEX_COLUMNS
from app.domain.regimes import CombustionRegime

SOURCE_ID = "PSI-69"
EN_DASH = "–"
FUELS = ("Methanol", "Heptane")

# Analysis choices (not physical limits) - documented in docs/10.
PRESSURE_CLUSTER_GAP_MMHG = 100.0  # split sorted valid pressures where consecutive gap exceeds this
COMPOSITION_SUM_TOLERANCE = 0.02  # report-only flag; table omits H2O/fuel vapour and is rounded
MIN_N_FOR_RANK_CORRELATION = 5
# NASA nominal design pressures (NASA/TP-2015-216046 sec. 1 and Tables I-VIII), used only to LABEL the
# observed clusters; the clusters are identical for gap rules of 25-200 mmHg (docs/11).
NOMINAL_PRESSURES_ATM = (0.70, 1.00, 2.03, 2.72, 3.05)
# Rows used for labelled sensitivity comparisons (never removed from primary results).
SENSITIVITY_TAGS = ("shutter_1_30s_period", "reported_K_0.05_short_translated_burn")

# Raw header -> canonical field for every column used here (raw headers preserved in the file).
EXTRA_COLUMNS = {
    "FLEX Test #": "psi_row",
    "FLEX Identifier": "identifier",
    "Test Date": "test_date",
    "Test GMT": "test_time_gmt",
    "Fuel": "fuel",
    "Burn time; s": "burn_time_s",
    "Test end": "test_end",
}
NUMERIC_FIELDS = (
    "ambient_pressure",
    "ambient_oxygen_mole_fraction",
    "ambient_nitrogen_mole_fraction",
    "co2_mole_fraction",
    "ambient_helium_mole_fraction",
    "initial_droplet_diameter",
    "extinction_diameter",
    "burning_rate_constant_mm2_s",
    "burn_time_s",
)
COMPOSITION = (
    "ambient_oxygen_mole_fraction",
    "ambient_nitrogen_mole_fraction",
    "co2_mole_fraction",
    "ambient_helium_mole_fraction",
)
SHORT = {
    "ambient_pressure": "P_mmHg",
    "ambient_oxygen_mole_fraction": "X_O2",
    "ambient_nitrogen_mole_fraction": "X_N2",
    "co2_mole_fraction": "X_CO2",
    "ambient_helium_mole_fraction": "X_He",
    "initial_droplet_diameter": "D0_mm",
    "extinction_diameter": "Dext_mm",
    "burning_rate_constant_mm2_s": "K_reported_mm2_s",
    "burn_time_s": "burn_time_s",
}


class IntegrityError(RuntimeError):
    pass


@dataclass
class FlexRun:
    psi_row: int
    identifier: str
    test_date: str
    test_time_gmt: str
    fuel: str
    test_end: str
    raw: dict[str, str]
    values: dict[str, float | None]
    field_flags: dict[str, list[str]] = field(default_factory=dict)
    row_flags: list[str] = field(default_factory=list)
    diluent_family: str = "unknown"
    pressure_cluster: str | None = None
    composition_sum: float | None = None
    pressure_cluster_lo: float | None = None
    flex_test_number: int | None = None
    record_key: str = ""
    support_mode: str = "unknown"
    dext_origin: str = ""
    sensitivity_tags: list[str] = field(default_factory=list)
    enrichment: dict[str, str] = field(default_factory=dict)

    def usable(self, name: str) -> bool:
        v = self.values.get(name)
        bad = {"missing_blank", "missing_dash_marker", "unparseable", "invalid_nonpositive_pressure"}
        return v is not None and not (set(self.field_flags.get(name, [])) & bad)


# ---------------------------------------------------------------- loading & integrity


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_entry(manifest: Path, source_id: str = SOURCE_ID) -> dict[str, str]:
    with manifest.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["source_id"] == source_id]
    if len(rows) != 1:
        raise IntegrityError(f"expected exactly one manifest row for {source_id}, found {len(rows)}")
    return rows[0]


def verify_artifact(raw_bytes: bytes, entry: dict[str, str]) -> str:
    digest = sha256_bytes(raw_bytes)
    if digest != entry["sha256"]:
        raise IntegrityError(
            f"SHA-256 mismatch for {entry['relative_path']}: {digest} != manifest {entry['sha256']}"
        )
    if len(raw_bytes) != int(entry["byte_size"]):
        raise IntegrityError("byte size differs from manifest")
    return digest


def parse_value(raw: str) -> tuple[float | None, list[str]]:
    s = raw.strip()
    if s == "":
        return None, ["missing_blank"]
    if s == EN_DASH:
        return None, ["missing_dash_marker"]
    flags: list[str] = []
    if s.startswith("~"):
        flags.append("approximate")
        s = s[1:].strip()
    try:
        return float(s), flags
    except ValueError:
        return None, [*flags, "unparseable"]


def parse_table(raw_bytes: bytes) -> list[FlexRun]:
    text = raw_bytes.decode("cp1252")  # verified encoding of the PSI-69 export
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    colmap: dict[int, str] = {}
    for idx, h in enumerate(header):
        if h in FLEX_COLUMNS:
            colmap[idx] = FLEX_COLUMNS[h].canonical
        elif h in EXTRA_COLUMNS:
            colmap[idx] = EXTRA_COLUMNS[h]
        else:
            raise IntegrityError(f"unmapped raw header: {h!r}")
    runs: list[FlexRun] = []
    for row in reader:
        rec = {colmap[i]: v for i, v in enumerate(row)}
        values: dict[str, float | None] = {}
        flags: dict[str, list[str]] = {}
        for name in NUMERIC_FIELDS:
            values[name], flags[name] = parse_value(rec.get(name, ""))
        runs.append(
            FlexRun(
                psi_row=int(rec["psi_row"]),
                identifier=rec["identifier"].strip(),
                test_date=rec["test_date"].strip(),
                test_time_gmt=rec["test_time_gmt"].strip(),
                fuel=rec["fuel"].strip(),
                test_end=rec["test_end"].strip(),
                raw={k: v for k, v in rec.items()},
                values=values,
                field_flags=flags,
            )
        )
    annotate(runs)
    return runs


def load_verified(raw_path: Path, manifest: Path) -> tuple[list[FlexRun], dict[str, str]]:
    data = raw_path.read_bytes()
    entry = manifest_entry(manifest)
    verify_artifact(data, entry)
    return parse_table(data), entry


# ---------------------------------------------------------------- quality annotation


def pressure_clusters(
    pressures: list[float], gap: float = PRESSURE_CLUSTER_GAP_MMHG
) -> list[tuple[float, float]]:
    vals = sorted(pressures)
    if not vals:
        return []
    clusters = [[vals[0], vals[0]]]
    for v in vals[1:]:
        if v - clusters[-1][1] > gap:
            clusters.append([v, v])
        else:
            clusters[-1][1] = v
    return [(lo, hi) for lo, hi in clusters]


def cluster_label(lo: float, hi: float) -> str:
    rng = f"{lo:g}-{hi:g} mmHg" if lo != hi else f"{lo:g} mmHg"
    mid = (lo + hi) / 2 / 760.0
    near = min(NOMINAL_PRESSURES_ATM, key=lambda a: abs(a - mid))
    return f"~{near:g} atm nominal ({rng})" if abs(near - mid) <= 0.05 else rng


def annotate(runs: list[FlexRun]) -> None:
    ids = Counter(r.identifier for r in runs)
    for r in runs:
        p = r.values["ambient_pressure"]
        if p is not None and p <= 0:
            r.field_flags["ambient_pressure"].append("invalid_nonpositive_pressure")
        if ids[r.identifier] > 1:
            r.row_flags.append("duplicate_source_identifier")
        if not r.test_time_gmt:
            r.row_flags.append("missing_test_time_gmt")
        if r.values["extinction_diameter"] == 0.0:
            r.field_flags["extinction_diameter"].append("zero_value_meaning_unconfirmed")
        comp = [r.values[c] for c in COMPOSITION]
        if all(v is not None for v in comp):
            total = round(sum(v for v in comp if v is not None), 6)
            r.composition_sum = total
            if abs(total - 1.0) > COMPOSITION_SUM_TOLERANCE:
                r.row_flags.append("composition_sum_deviation")
            co2, he = r.values["co2_mole_fraction"], r.values["ambient_helium_mole_fraction"]
            assert co2 is not None and he is not None
            r.diluent_family = (
                "N2_only"
                if co2 == 0 and he == 0
                else "CO2_added"
                if co2 > 0 and he == 0
                else "He_added"
                if he > 0 and co2 == 0
                else "CO2_and_He"
            )
        if r.fuel not in FUELS:
            r.row_flags.append("unexpected_fuel")
    valid_p = [r.values["ambient_pressure"] for r in runs if r.usable("ambient_pressure")]
    clusters = pressure_clusters([p for p in valid_p if p is not None])
    for r in runs:
        if r.usable("ambient_pressure"):
            p = r.values["ambient_pressure"]
            for lo, hi in clusters:
                if p is not None and lo <= p <= hi:
                    r.pressure_cluster = cluster_label(lo, hi)
                    r.pressure_cluster_lo = lo
    for r in runs:
        r.dext_origin = classify_dext(r, None)
        if (
            r.values["extinction_diameter"]
            and r.values["initial_droplet_diameter"]
            and ((r.values["extinction_diameter"] or 0) > (r.values["initial_droplet_diameter"] or 0))
        ):
            r.row_flags.append("dext_exceeds_d0")


def classify_dext(r: FlexRun, caption_note: str | None) -> str:
    """Measurement origin of the visible flame extinction diameter (NASA/TP-2015-216046 App. A.1).

    A.1: '-' means flame extinction did not occur (completion or disruption); a diameter is not listed
    when the droplet was not in the HiBMs view long enough; some diameters were extrapolated.
    caption_note None = enrichment not loaded (extrapolation status unknown).
    """
    flags = r.field_flags.get("extinction_diameter", [])
    v = r.values["extinction_diameter"]
    ext = r.test_end == "Extinction"
    if "missing_dash_marker" in flags:
        return "inconsistent_dash_with_extinction_end" if ext else "not_applicable_no_extinction_per_A1"
    if "missing_blank" in flags:
        return "not_listed_insufficient_view_per_A1"
    if v == 0.0:
        return "zero_semantics_unconfirmed"
    if not ext:
        return "value_with_non_extinction_end_semantics_unclear"
    if caption_note is None:
        return "reported_extinction_extrapolation_unknown"
    if caption_note == "caption_mentions_extrapolation":
        return "reported_extinction_extrapolation_noted_in_caption"
    return "reported_extinction_no_extrapolation_noted"


def attach_enrichment(runs: list[FlexRun], path: Path) -> str:
    """Attach data/derived/flex_enrichment_v1.csv (keyed by PSI row; identity cross-checked)."""
    data = path.read_bytes()
    rows = {int(e["psi_row"]): e for e in csv.DictReader(io.StringIO(data.decode("utf-8")))}
    if set(rows) != {r.psi_row for r in runs}:
        raise IntegrityError("enrichment rows do not cover exactly the PSI rows")
    for r in runs:
        e = rows[r.psi_row]
        if e["identifier"] != r.identifier or e["test_date_psi"] != r.test_date:
            raise IntegrityError(f"enrichment identity mismatch at PSI row {r.psi_row}")
        r.enrichment = dict(e)
        r.flex_test_number = int(e["flex_test_number"])
        r.record_key = e["record_key"]
        r.support_mode = e["support_mode"]
        r.dext_origin = classify_dext(r, e["dext_caption_note"])
        if e["shutter_1_30s_period"] == "True":
            r.sensitivity_tags.append("shutter_1_30s_period")
        if r.flex_test_number == 130:
            r.sensitivity_tags.append("reported_K_0.05_short_translated_burn")
    return sha256_bytes(data)


# ---------------------------------------------------------------- statistics


def _rank(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation with average ties; None if n < MIN_N or no variation."""
    if len(x) != len(y) or len(x) < MIN_N_FOR_RANK_CORRELATION:
        return None
    rx, ry = _rank(np.asarray(x, float)), _rank(np.asarray(y, float))
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def describe(vals: list[float]) -> dict[str, float | int | None]:
    if not vals:
        return {
            "n": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
            "mean": None,
            "sd": None,
        }
    a = np.asarray(vals, float)
    return {
        "n": int(a.size),
        "min": float(a.min()),
        "q1": float(np.quantile(a, 0.25)),
        "median": float(np.median(a)),
        "q3": float(np.quantile(a, 0.75)),
        "max": float(a.max()),
        "mean": float(a.mean()),
        "sd": float(a.std(ddof=1)) if a.size > 1 else None,
    }


# ---------------------------------------------------------------- comparison-gate use


def descriptor(r: FlexRun, variable: str = "burning_rate_constant_mm2_s") -> ObservationDescriptor:
    conds = {}
    p = r.values["ambient_pressure"]
    if r.usable("ambient_pressure") and p is not None:
        conds["ambient_pressure"] = Condition(value=p, unit="mmHg")
    for c in COMPOSITION:
        v = r.values[c]
        if r.usable(c) and v is not None:
            conds[c] = Condition(value=v, unit="mole_fraction")
    return ObservationDescriptor(
        investigation_id=SOURCE_ID,
        regime=CombustionRegime.FLEX_DROPLET,
        variable=variable,
        unit="mm^2/s",
        material_or_fuel=r.fuel,
        apparatus="MDCA",
        conditions=conds,
    )


def _vals(rows: list[FlexRun], name: str) -> list[float]:
    return [v for r in rows if r.usable(name) and (v := r.values[name]) is not None]


def replicate_groups(runs: list[FlexRun]) -> list[dict[str, Any]]:
    """Groups of runs the comparison gate classifies pairwise as DIRECT (same fuel and environment)."""
    out = []
    for fuel in FUELS:
        pool = [r for r in runs if r.fuel == fuel and r.usable("burning_rate_constant_mm2_s")]
        groups: list[list[FlexRun]] = []
        for r in pool:
            for g in groups:
                res = validate_comparison(descriptor(g[0]), descriptor(r))
                if res.classification is ComparisonClass.DIRECT:
                    g.append(r)
                    break
            else:
                groups.append([r])
        for g in groups:
            if len(g) >= 2:
                ks = [x.values["burning_rate_constant_mm2_s"] for x in g]
                out.append(
                    {
                        "fuel": fuel,
                        "psi_rows": [x.psi_row for x in g],
                        "environment": {SHORT[c]: g[0].values[c] for c in ("ambient_pressure", *COMPOSITION)},
                        "K_reported_mm2_s": ks,
                        "D0_mm": [x.values["initial_droplet_diameter"] for x in g],
                        "test_end": [x.test_end for x in g],
                    }
                )
    return out


def cross_fuel_gate_check(runs: list[FlexRun]) -> dict[str, Any]:
    """Confirms the gate never allows a shared axis between fuels for these runs."""
    by_fuel = {f: [r for r in runs if r.fuel == f] for f in FUELS}
    counts: Counter[str] = Counter()
    for a in by_fuel["Methanol"]:
        for b in by_fuel["Heptane"]:
            counts[validate_comparison(descriptor(a), descriptor(b)).classification.value] += 1
    return {
        "pairs": sum(counts.values()),
        "classification_counts": dict(counts),
        "shared_axis_allowed_pairs": counts.get("direct", 0) + counts.get("controlled_variation", 0),
    }


# ---------------------------------------------------------------- analyses


@dataclass
class StratumResult:
    analysis: str
    fuel: str
    stratum: dict[str, object]
    x: str
    y: str
    n: int
    rho_spearman: float | None
    x_summary: dict[str, float | int | None]
    y_summary: dict[str, float | int | None]
    psi_rows: list[int]
    note: str = ""
    n_values_in_x_ties: int = 0
    n_values_in_y_ties: int = 0
    sensitivity_rows: list[int] = field(default_factory=list)
    rho_without_sensitivity_rows: float | None = None
    evidence_class: str = "descriptive_exploratory"


def _exclusions(rows: list[FlexRun], needed: list[str]) -> tuple[list[FlexRun], Counter[str]]:
    kept: list[FlexRun] = []
    why: Counter[str] = Counter()
    for r in rows:
        bad = [n for n in needed if not r.usable(n)]
        if bad:
            for n in bad:
                flags = r.field_flags.get(n) or ["missing"]
                why[f"{SHORT.get(n, n)}:{'+'.join(flags)}"] += 1
        else:
            kept.append(r)
    return kept, why


def _strata_result(
    analysis: str, fuel: str, stratum: dict[str, object], rows: list[FlexRun], x: str, y: str, note: str = ""
) -> StratumResult:
    xs = [r.values[x] for r in rows]
    ys = [r.values[y] for r in rows]
    xf = [v for v in xs if v is not None]
    yf = [v for v in ys if v is not None]
    res = StratumResult(
        analysis,
        fuel,
        stratum,
        SHORT[x],
        SHORT[y],
        len(rows),
        spearman(xf, yf),
        describe(xf),
        describe(yf),
        sorted(r.psi_row for r in rows),
        note,
    )
    res.n_values_in_x_ties = sum(c for c in Counter(xf).values() if c > 1)
    res.n_values_in_y_ties = sum(c for c in Counter(yf).values() if c > 1)
    sens = [r for r in rows if r.sensitivity_tags]
    if sens:
        res.sensitivity_rows = sorted(r.psi_row for r in sens)
        rest = [r for r in rows if not r.sensitivity_tags]
        res.rho_without_sensitivity_rows = spearman(
            [v for r in rest if (v := r.values[x]) is not None],
            [v for r in rest if (v := r.values[y]) is not None],
        )
    return res


def _group(rows: list[FlexRun], key) -> dict[tuple, list[FlexRun]]:
    g: dict[tuple, list[FlexRun]] = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return dict(sorted(g.items(), key=lambda kv: str(kv[0])))


K = "burning_rate_constant_mm2_s"
O2 = "ambient_oxygen_mole_fraction"


def run_analyses(runs: list[FlexRun]) -> dict[str, Any]:
    results: list[StratumResult] = []
    exclusions: dict[str, dict[str, dict[str, int]]] = {}
    comp_needed = ["ambient_pressure", *COMPOSITION]

    def record(name: str, fuel: str, why: Counter[str]) -> None:
        exclusions.setdefault(name, {})[fuel] = dict(why)

    for fuel in FUELS:
        fr = [r for r in runs if r.fuel == fuel]

        # A1 O2 vs reported K: N2 is the only balance gas -> O2 is the single compositional DOF.
        kept, why = _exclusions(fr, [K, *comp_needed])
        record("A1_O2_vs_K", fuel, why)
        for (fam, pc, sm), rows in _group(
            kept, lambda r: (r.diluent_family, r.pressure_cluster, r.support_mode)
        ).items():
            if fam == "N2_only":
                stratum = {"diluent_family": fam, "pressure_cluster": pc, "support_mode": sm}
                results.append(
                    _strata_result(
                        "A1_O2_vs_K",
                        fuel,
                        stratum,
                        rows,
                        O2,
                        K,
                        note="pressure varies within cluster; D0 and test date vary",
                    )
                )

        # A2/A3 CO2 or He vs reported K at fixed O2 (CO2/He trade against N2: one DOF).
        for name, fam_name, xvar in (
            ("A2_CO2_vs_K", "CO2_added", "co2_mole_fraction"),
            ("A3_He_vs_K", "He_added", "ambient_helium_mole_fraction"),
        ):
            record(name, fuel, why)
            groups = _group(
                kept, lambda r: (r.diluent_family, r.pressure_cluster, r.values[O2], r.support_mode)
            )
            for (fam, pc, o2, sm), rows in groups.items():
                if fam != fam_name:
                    continue
                # zero-diluent reference: N2-only runs at the same O2 and pressure cluster
                ref = [
                    r
                    for r in kept
                    if r.diluent_family == "N2_only"
                    and r.pressure_cluster == pc
                    and r.values[O2] == o2
                    and r.support_mode == sm
                ]
                stratum = {
                    "pressure_cluster": pc,
                    "X_O2_fixed": o2,
                    "support_mode": sm,
                    "includes_zero_diluent_reference_runs": len(ref),
                }
                results.append(
                    _strata_result(
                        name,
                        fuel,
                        stratum,
                        rows + ref,
                        xvar,
                        K,
                        note="confounded: N2 varies with the added diluent; reference "
                        "runs from other test days; pressure varies in cluster",
                    )
                )

        # A4 pressure vs reported K at fixed O2 within N2-only runs.
        record("A4_P_vs_K", fuel, why)
        for (fam, o2, sm), rows in _group(
            kept, lambda r: (r.diluent_family, r.values[O2], r.support_mode)
        ).items():
            if fam == "N2_only" and len({r.pressure_cluster for r in rows}) >= 2:
                res = _strata_result(
                    "A4_P_vs_K",
                    fuel,
                    {"diluent_family": fam, "X_O2_fixed": o2, "support_mode": sm},
                    rows,
                    "ambient_pressure",
                    K,
                )
                res.stratum["by_pressure_cluster"] = {
                    pc: describe(_vals(grp, K))
                    for (pc,), grp in _group(rows, lambda r: (r.pressure_cluster,)).items()
                }
                results.append(res)

        # A5 D0 vs reported K within diluent family x pressure cluster (O2 varies: confounded, noted).
        kept5, why5 = _exclusions(fr, [K, "initial_droplet_diameter", *comp_needed])
        record("A5_D0_vs_K", fuel, why5)
        for (fam, pc, sm), rows in _group(
            kept5, lambda r: (r.diluent_family, r.pressure_cluster, r.support_mode)
        ).items():
            stratum = {"diluent_family": fam, "pressure_cluster": pc, "support_mode": sm}
            results.append(
                _strata_result(
                    "A5_D0_vs_K",
                    fuel,
                    stratum,
                    rows,
                    "initial_droplet_diameter",
                    K,
                    note="confounded: O2 and diluent level vary within stratum",
                )
            )

        # A6 O2 vs visible flame extinction diameter: extinction outcome only, N2-only.
        # Eligible population (docs/11): test end = Extinction AND a positive reported diameter whose
        # caption does not note extrapolation. Every other row is counted by its dext_origin.
        eligible_origin = (
            "reported_extinction_no_extrapolation_noted",
            "reported_extinction_extrapolation_unknown",
        )
        why6 = Counter(f"dext_origin:{r.dext_origin}" for r in fr if r.dext_origin not in eligible_origin)
        elig = [r for r in fr if r.dext_origin in eligible_origin]
        kept6, why_c = _exclusions(elig, comp_needed)
        why6.update(why_c)
        record("A6_O2_vs_Dext", fuel, why6)
        for (fam, pc, sm), rows in _group(
            kept6, lambda r: (r.diluent_family, r.pressure_cluster, r.support_mode)
        ).items():
            if fam == "N2_only":
                stratum = {"diluent_family": fam, "pressure_cluster": pc, "support_mode": sm}
                results.append(
                    _strata_result(
                        "A6_O2_vs_Dext",
                        fuel,
                        stratum,
                        rows,
                        O2,
                        "extinction_diameter",
                        note="D0 also varies; extinction diameter depends on D0",
                    )
                )

    outcomes = outcome_tables(runs)
    return {
        "strata": [r.__dict__ for r in results],
        "exclusions": exclusions,
        "outcomes": outcomes,
        "replicate_groups": replicate_groups(runs),
        "cross_fuel_gate_check": cross_fuel_gate_check(runs),
    }


def outcome_tables(runs: list[FlexRun]) -> dict[str, Any]:
    counts: dict[str, dict[str, dict[str, int]]] = {}
    conditions: dict[str, dict[str, dict[str, object]]] = {}
    for fuel in FUELS:
        fr = [r for r in runs if r.fuel == fuel]
        c: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in fr:
            c[f"{r.diluent_family} | {r.pressure_cluster or 'pressure_invalid'}"][r.test_end] += 1
        counts[fuel] = {k: dict(v) for k, v in sorted(c.items())}
        conditions[fuel] = {}
        for end in sorted({r.test_end for r in fr}):
            grp = [r for r in fr if r.test_end == end]
            conditions[fuel][end] = {
                SHORT[v]: describe(_vals(grp, v))
                for v in (
                    "ambient_oxygen_mole_fraction",
                    "initial_droplet_diameter",
                    "ambient_pressure",
                    "co2_mole_fraction",
                    "ambient_helium_mole_fraction",
                )
            }
    caveats = {
        "Methanol": "NASA/TP-2015-216046 sec. 5.2 item 4: disruptive extinction of methanol is probably due "
        "to needle-coating contamination (all tests in the report used coated needles). Methanol "
        "disruption counts must not be read as a response to ambient conditions.",
        "Heptane": "sec. 5.2 item 5: heptane disruption may be due to the contaminant; NASA states no "
        "conclusion can be drawn regarding disruptive burning for heptane in these tests.",
    }
    return {
        "counts_by_family_and_pressure_cluster": counts,
        "condition_summary_by_outcome": conditions,
        "contamination_caveats": caveats,
    }


# ---------------------------------------------------------------- quality & coverage


def quality_report(runs: list[FlexRun]) -> dict[str, Any]:
    cov: dict[str, dict[str, dict[str, int]]] = {}
    for fuel in FUELS:
        fr = [r for r in runs if r.fuel == fuel]
        cov[fuel] = {}
        for name in NUMERIC_FIELDS:
            flags = Counter(f for r in fr for f in r.field_flags.get(name, []))
            usable = sum(r.usable(name) for r in fr)
            cov[fuel][SHORT[name]] = {"rows": len(fr), "usable": usable, **dict(flags)}
    row_flags = Counter(f for r in runs for f in r.row_flags)
    return {
        "rows_total": len(runs),
        "rows_by_fuel": dict(Counter(r.fuel for r in runs)),
        "rows_by_test_end": dict(Counter(r.test_end for r in runs)),
        "rows_by_diluent_family": {
            f: dict(Counter(r.diluent_family for r in runs if r.fuel == f)) for f in FUELS
        },
        "pressure_clusters": dict(Counter(r.pressure_cluster or "pressure_invalid" for r in runs)),
        "row_flag_counts": dict(row_flags),
        "flagged_rows": [
            {
                "psi_row": r.psi_row,
                "identifier": r.identifier,
                "fuel": r.fuel,
                "row_flags": r.row_flags,
                "composition_sum": r.composition_sum,
                "field_flags": {SHORT[k]: v for k, v in r.field_flags.items() if v},
            }
            for r in runs
            if r.row_flags or any(r.field_flags.values())
        ],
        "variable_coverage_by_fuel": cov,
        "pressure_distribution": {
            "valid_min_mmHg": min(_vals(runs, "ambient_pressure")),
            "valid_max_mmHg": max(_vals(runs, "ambient_pressure")),
            "by_fuel_family_cluster": {
                f: dict(
                    Counter(
                        f"{r.diluent_family} | {r.pressure_cluster or 'pressure_invalid'}"
                        for r in runs
                        if r.fuel == f
                    )
                )
                for f in FUELS
            },
            "records_above_1000_mmHg": [
                {
                    "psi_row": r.psi_row,
                    "flex": r.flex_test_number,
                    "fuel": r.fuel,
                    "P_mmHg": r.values["ambient_pressure"],
                    "composition": [r.values[c] for c in COMPOSITION],
                    "K": r.values["burning_rate_constant_mm2_s"],
                    "test_end": r.test_end,
                }
                for r in runs
                if (r.values["ambient_pressure"] or 0) > 1000
            ],
            "invalid": [
                {
                    "psi_row": r.psi_row,
                    "flex": r.flex_test_number,
                    "raw": r.raw.get("ambient_pressure"),
                    "source_conflict": r.enrichment.get("pressure_source_conflict", ""),
                }
                for r in runs
                if not r.usable("ambient_pressure")
            ],
        },
        "support_mode_by_fuel": {
            f: dict(Counter(r.support_mode for r in runs if r.fuel == f)) for f in FUELS
        },
        "dext_origin_by_fuel": {f: dict(Counter(r.dext_origin for r in runs if r.fuel == f)) for f in FUELS},
        "sensitivity_rows": {
            t: [r.psi_row for r in runs if t in r.sensitivity_tags] for t in SENSITIVITY_TAGS
        },
    }


def descriptive_by_fuel(runs: list[FlexRun]) -> dict[str, dict[str, Any]]:
    return {
        fuel: {SHORT[n]: describe(_vals([r for r in runs if r.fuel == fuel], n)) for n in NUMERIC_FIELDS}
        for fuel in FUELS
    }


def row_table(runs: list[FlexRun]) -> list[dict[str, object]]:
    """All rows (none dropped) with canonical values and flags - a derived view, not a raw edit."""
    out = []
    for r in runs:
        row: dict[str, object] = {
            "psi_row": r.psi_row,
            "record_key": r.record_key,
            "flex_test_number": r.flex_test_number or "",
            "support_mode": r.support_mode,
            "dext_origin": r.dext_origin,
            "sensitivity_tags": ";".join(r.sensitivity_tags),
            "identifier": r.identifier,
            "fuel": r.fuel,
            "test_end": r.test_end,
            "diluent_family": r.diluent_family,
            "pressure_cluster": r.pressure_cluster or "",
        }
        for n in NUMERIC_FIELDS:
            v = r.values[n]
            row[SHORT[n]] = "" if v is None else v
            row[SHORT[n] + "_flags"] = ";".join(r.field_flags.get(n, []))
        row["composition_sum"] = "" if r.composition_sum is None else r.composition_sum
        row["row_flags"] = ";".join(r.row_flags)
        out.append(row)
    return out
