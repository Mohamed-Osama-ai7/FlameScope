"""Flame Vision & Metrology: acquire FLEX HIBMS test bundles and run the scale-free evaluation.

From the repository root:
    python backend/scripts/run_flame_vision.py fetch 20CAL10 20CAL12 30CAL06   # ~1 GB, PSI public files
    python backend/scripts/run_flame_vision.py run   20CAL10 20CAL12 30CAL06

``fetch`` reuses fetch_psi_table.py (host allow-list, size check, immutable store) and records every file
in data/metadata/vision_artifact_manifest.csv. ``run`` verifies each file against that manifest (SHA-256
+ size) before reading it, reads frames from the zip in place, and writes
data/derived/flame_vision/<test>/{summary.json, series.csv, d2_curve.svg, overlay.png}.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.client
import json
import sys
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import fetch_psi_table as psi  # noqa: E402

from app.analysis import flex_run_level as flex  # noqa: E402
from app.vision.eligibility import evidence_eligibility, reference_eligibility  # noqa: E402
from app.vision.method_card import HIBMS_DROPLET_CARD  # noqa: E402
from app.vision.metrology import FrameRecord, evaluate  # noqa: E402
from app.vision.nasa_bundle import HibmsBundle, raw_dir  # noqa: E402
from app.vision.validation import occlusion_verdict, uncertainty_budget  # noqa: E402

ROOT = BACKEND.parent
CAL_DIR = Path("data/raw/PSI-69/calibration")
MANIFEST = ROOT / "data/metadata/vision_artifact_manifest.csv"
OUT_DIR = ROOT / "data/derived/flame_vision"
FIELDS = ["source_id", "test_point", "role", "file_name", "relative_path", "byte_size", "sha256",
          "source_url", "license", "retrieved_at_utc"]  # fmt: skip
ROLES = {"test_log": ".txt", "frame_index": "A.txt", "camera_settings": "_HIBMS_Camera_Settings.txt",
         "frames_zip": "A.zip"}  # fmt: skip


class ProvenanceError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest() -> list[dict[str, str]]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_manifest(rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda r: (r["test_point"], r["role"]))
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _download(url: str, attempts: int = 3) -> bytes:
    """PSI download with retries on dropped connections (a partial body is never stored)."""
    for i in range(attempts):
        try:
            body, ctype = psi._get(url, 120, 3)
            indirect, data = psi.resolve_payload(body, ctype)
            if indirect is not None:
                data, _ = psi._get(indirect, 3600, 2)
            assert data is not None
            return data
        except (http.client.IncompleteRead, ConnectionError, TimeoutError) as exc:
            if i + 1 == attempts:
                raise psi.FetchError(f"{url}: download interrupted {attempts} times: {exc!r}") from exc
            print(f"RETRY {url} after {type(exc).__name__}", flush=True)
    raise AssertionError("unreachable")


def fetch(tests: list[str]) -> None:
    rows = {r["relative_path"]: r for r in _manifest()}
    for test in tests:
        for role, suffix in ROLES.items():
            name = f"PSI-69_Calibration_{test}{suffix}"
            rel = CAL_DIR / name  # logical project path recorded in the manifest
            target = raw_dir() / name  # physical location (FLAMESCOPE_VISION_RAW_DIR)
            url = psi.download_url("PSI-69", name, 1)
            if not target.exists():
                data = _download(url)
                psi.store_immutable(target, data)
                retrieved = datetime.now(UTC)
            else:  # already acquired (immutable): record what is on disk
                retrieved = datetime.fromtimestamp(target.stat().st_mtime, UTC)
            row = rows.get(rel.as_posix())
            digest = _sha(target)
            if row and row["sha256"] != digest:
                raise ProvenanceError(f"{rel}: bytes differ from manifest; raw files are immutable")
            rows[rel.as_posix()] = row or {
                "source_id": "PSI-69", "test_point": test, "role": role, "file_name": name,
                "relative_path": rel.as_posix(), "byte_size": str(target.stat().st_size), "sha256": digest,
                "source_url": url, "license": "CC0-1.0",
                "retrieved_at_utc": retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }  # fmt: skip
            print(f"OK   {rel.as_posix()} sha256={digest[:16]}", flush=True)
    _write_manifest(list(rows.values()))


def verify(test: str) -> list[dict[str, str]]:
    rows = [r for r in _manifest() if r["test_point"] == test]
    if len(rows) != len(ROLES):
        raise ProvenanceError(f"{test}: manifest has {len(rows)} of {len(ROLES)} files; run `fetch {test}`")
    for r in rows:
        path = raw_dir() / r["file_name"]
        if not path.is_file():
            raise ProvenanceError(f"missing raw file {r['relative_path']} (run `fetch {test}`)")
        if path.stat().st_size != int(r["byte_size"]) or _sha(path) != r["sha256"]:
            raise ProvenanceError(f"{r['relative_path']}: SHA-256/size mismatch with manifest; refused")
    return rows


def nasa_reference(test: str) -> dict[str, object]:
    runs, entry = flex.load_verified(
        ROOT / "data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv",
        ROOT / "data/metadata/artifact_manifest.csv",
    )
    match = [r for r in runs if r.identifier == test]
    if len(match) != 1:
        raise ProvenanceError(f"{test}: expected one PSI-69 table row, found {len(match)}")
    r = match[0]
    k, d0, dext = (r.values[n] for n in ("burning_rate_constant_mm2_s", "initial_droplet_diameter",
                                          "extinction_diameter"))  # fmt: skip
    return {
        "run_id": f"PSI-69-r{r.psi_row:03d}",
        "flex_identifier": test,
        "fuel": r.fuel,
        "test_end": r.test_end,
        "reported_k_mm2_per_s": k,
        "reported_d0_mm": d0,
        "reported_extinction_diameter_mm": dext,
        "reported_burn_time_s": r.values["burn_time_s"],
        "reported_k_over_d0sq_per_s": (k / d0**2) if k and d0 else None,
        "reported_dext_over_d0": (dext / d0) if dext and d0 else None,
        "value_origin": "reported_in_source (FLEX team), PSI-69 experimental table sha256 "
        + entry["sha256"][:12],
    }


def _svg(records: list[FrameRecord], s: dict, test: str) -> str:
    pts = [(r.t_s, r.diameter_px**2) for r in records if r.status == "measured" and r.t_s is not None
           and r.diameter_px is not None and r.t_s > -1.0]  # fmt: skip
    w, h, pad = 640, 360, 50
    tmax = max(t for t, _ in pts)
    ymax = max(y for _, y in pts) * 1.05
    tmin = -1.0

    def X(t: float) -> float:
        return pad + (t - tmin) / (tmax - tmin) * (w - 2 * pad)

    def Y(y: float) -> float:
        return h - pad - y / ymax * (h - 2 * pad)

    f = s["fit"]
    t0, t1 = s["windows_s"]["fit"]
    dots = "".join(f'<circle cx="{X(t):.1f}" cy="{Y(y):.1f}" r="1.6" fill="#1f5fd1"/>' for t, y in pts)
    ex0, ex1 = s["windows_s"]["excluded_igniters"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'font-family="sans-serif" font-size="11">'
        f'<rect width="{w}" height="{h}" fill="#fff"/>'
        f'<rect x="{X(ex0):.1f}" y="{pad}" width="{X(ex1) - X(ex0):.1f}" height="{h - 2 * pad}" fill="#eee"/>'
        f'<text x="{X(ex0) + 2:.1f}" y="{pad + 12}" fill="#666">igniters in view (excluded)</text>'
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#333"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#333"/>'
        f"{dots}"
        f'<line x1="{X(t0):.1f}" y1="{Y(f["intercept"] + f["slope"] * t0):.1f}" x2="{X(t1):.1f}" '
        f'y2="{Y(f["intercept"] + f["slope"] * t1):.1f}" stroke="#b42318" stroke-width="2"/>'
        f'<line x1="{X(s["regime_break_t_s"]):.1f}" y1="{pad}" x2="{X(s["regime_break_t_s"]):.1f}" '
        f'y2="{h - pad}" stroke="#a15c00" stroke-dasharray="4 3"/>'
        f'<text x="{w / 2:.0f}" y="{h - 12}" text-anchor="middle">time from igniter-on (s)</text>'
        f'<text x="14" y="{h / 2:.0f}" transform="rotate(-90 14 {h / 2:.0f})" text-anchor="middle">'
        f"D^2 (px^2)</text>"
        f'<text x="{pad + 8}" y="{pad - 14}">FLEX {test} HIBMS: D^2(t) in pixels; red = fit, dashed = '
        f"droplet regime break; K/D0^2 = {s['k_over_d0sq_per_s']:.4f} 1/s</text>"
        f'<text x="{pad - 6}" y="{h - pad + 4}" text-anchor="end">0</text>'
        f'<text x="{pad - 6}" y="{pad + 4}" text-anchor="end">{ymax:.0f}</text>'
        f'<text x="{X(0):.1f}" y="{h - pad + 14}" text-anchor="middle">0</text>'
        f'<text x="{w - pad}" y="{h - pad + 14}" text-anchor="middle">{tmax:.0f}</text>'
        "</svg>"
    )


def _overlay(bundle: HibmsBundle, records: list[FrameRecord], path: Path) -> None:
    import cv2
    import numpy as np

    measured = [r for r in records if r.status == "measured" and r.t_s is not None and r.t_s > 1.5]
    picks = [measured[0], measured[len(measured) // 3], measured[2 * len(measured) // 3]]
    tiles = []
    for r in picks:
        img = bundle.read_frame(r.frame + ".tif")
        if img is None or r.centroid_x_px is None or r.centroid_y_px is None or r.diameter_px is None:
            continue
        grey = ((img - img.min()) * (255.0 / max(float(img.max() - img.min()), 1.0))).astype(np.uint8)
        v = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
        cx, cy, rad = int(round(r.centroid_x_px)), int(round(r.centroid_y_px)), r.diameter_px / 2
        cv2.circle(v, (cx, cy), int(round(rad)), (40, 40, 220), 1)
        crop = v[max(0, cy - 40) : cy + 40, max(0, cx - 40) : cx + 40]
        crop = cv2.resize(crop, (240, 240), interpolation=cv2.INTER_NEAREST)
        cv2.putText(crop, f"t={r.t_s:.2f}s D={r.diameter_px:.1f}px", (6, 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (40, 40, 220), 1)  # fmt: skip
        tiles.append(crop)
    cv2.imwrite(str(path), np.hstack(tiles))


def write_abstention(test: str, reason: str, files: list[dict[str, str]]) -> None:
    out = OUT_DIR / test
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("series.csv", "d2_curve.svg", "overlay.png", "evidence.png"):
        (out / stale).unlink(missing_ok=True)
    summary = {
        "test_point": test,
        "method": {
            "method_id": HIBMS_DROPLET_CARD.method_id,
            "version": HIBMS_DROPLET_CARD.version,
            "status": HIBMS_DROPLET_CARD.status,
        },  # fmt: skip
        "evidence_eligibility": evidence_eligibility(ROOT),
        "reference_eligibility": reference_eligibility(ROOT),
        "computable": False,
        "abstention_reason": reason,
        "nasa_reference": nasa_reference(test),
        "provenance": files,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", "utf-8")


def _evidence(bundle: HibmsBundle, records: list[FrameRecord], s: dict, path: Path) -> None:
    """Original / threshold mask / overlay for a mid-burn frame and for a frame inside the igniter window."""
    import cv2
    import numpy as np

    from app.vision.segmentation import SegmentationParams, segment_droplet

    t0, t1 = s["windows_s"]["fit"]
    ex0, ex1 = s["windows_s"]["excluded_igniters"]
    by_t = [r for r in records if r.t_s is not None]
    picks = [
        (
            "burning",
            min((r for r in by_t if r.status == "measured"), key=lambda r: abs(r.t_s - (t0 + t1) / 2)),
        ),  # type: ignore[operator]
        ("igniter window", min(by_t, key=lambda r: abs(r.t_s - (ex0 + ex1) / 2))),  # type: ignore[operator]
    ]
    params = SegmentationParams(**s["segmentation_params"])
    rows = []
    for label, r in picks:
        img = bundle.read_frame(r.frame + ".tif")
        if img is None:
            continue
        grey = ((img - img.min()) * (255.0 / max(float(img.max() - img.min()), 1.0))).astype(np.uint8)
        mask = ((img < params.threshold_fraction * float(np.median(img))) * 255).astype(np.uint8)
        over = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
        det = segment_droplet(img, params)
        if det is not None:
            cv2.circle(over, (round(det.centroid_x_px), round(det.centroid_y_px)),
                       round(det.equivalent_diameter_px / 2), (40, 40, 220), 2)  # fmt: skip
        tiles = [cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR), cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), over]
        tiles = [cv2.resize(t, (256, 256), interpolation=cv2.INTER_AREA) for t in tiles]
        for tile, name in zip(
            tiles, ("original", f"mask f={params.threshold_fraction:.1f}", "overlay"), strict=True
        ):
            cv2.putText(tile, f"{label} t={r.t_s:.2f}s {name}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (40, 40, 220), 1)  # fmt: skip
        rows.append(np.hstack(tiles))
    if rows:
        cv2.imwrite(str(path), np.vstack(rows))


def write_evaluation() -> dict:
    """Cross-test table from every stored summary (data/derived/flame_vision/evaluation.json)."""
    rows = []
    for path in sorted(OUT_DIR.glob("*/summary.json")):
        s = json.loads(path.read_text("utf-8"))
        ref = s["nasa_reference"]
        if s.get("computable") is False:
            rows.append({"test_point": s["test_point"], "run_id": ref["run_id"], "fuel": ref["fuel"],
                         "test_end": ref["test_end"], "computable": False,
                         "abstention_reason": s["abstention_reason"]})  # fmt: skip
            continue
        c, r = s["comparison"], s["results"]
        rows.append({
            "test_point": s["test_point"], "run_id": ref["run_id"], "fuel": ref["fuel"],
            "test_end": ref["test_end"], "computable": True, "fit_frames": r["fit"]["n"],
            "fit_r_squared": r["fit"]["r_squared"], "fit_window_coverage": r["fit_window_coverage"],
            "vision_k_over_d0sq_per_s": c["vision_k_over_d0sq_per_s"],
            "vision_rel_uncertainty_1sigma": r["k_over_d0sq_rel_uncertainty_1sigma"],
            "threshold_sensitivity": r["threshold_sensitivity_k_over_d0sq"],
            "nasa_k_over_d0sq_per_s": c["nasa_k_over_d0sq_per_s"],
            "relative_difference": c["relative_difference"],
            "implied_mm_per_px_from_nasa_d0": c["implied_mm_per_px_from_nasa_d0"],
            "occlusion_verdict": c["occlusion_assessment"]["verdict"],
            "hidden_part_of_nasa_window_s": c["occlusion_assessment"].get("hidden_part_of_nasa_window_s"),
            "required_hidden_k_over_d0sq_per_s": c["occlusion_assessment"].get(
                "required_hidden_k_over_d0sq_per_s"
            ),
            "max_local_k_over_d0sq_per_s": r["diagnostics"]["max_local_k_over_d0sq_per_s"],
        })  # fmt: skip
    ok = [r for r in rows if r["computable"]]
    diffs = [r["relative_difference"] for r in ok if r["relative_difference"] is not None]
    scales = [r["implied_mm_per_px_from_nasa_d0"] for r in ok if r["implied_mm_per_px_from_nasa_d0"]]
    out = {
        "method_id": HIBMS_DROPLET_CARD.method_id,
        "method_version": HIBMS_DROPLET_CARD.version,
        "evidence_eligibility": evidence_eligibility(ROOT),
        "reference_eligibility": reference_eligibility(ROOT),
        "tests": rows,
        "n_tests": len(rows),
        "n_computable": len(ok),
        "n_abstained": len(rows) - len(ok),
        "relative_difference_mean": sum(diffs) / len(diffs) if diffs else None,
        "relative_difference_range": [min(diffs), max(diffs)] if diffs else None,
        "implied_scale_range_mm_per_px": [min(scales), max(scales)] if scales else None,
        "verdict": "not validated against the tabulated K: the vision K/D0^2 is 7-22% below it, mostly "
        "because "
        "the table normalises by a post-ignition D0 (docs/16 section 5). Cross-check on NASA's published "
        "D^2(t) curves (unregistered source): within about 3%, see nasa_report_crosscheck.json",
    }
    (OUT_DIR / "evaluation.json").write_text(json.dumps(out, indent=2) + "\n", "utf-8")
    return out


def run(tests: list[str]) -> int:
    failed = False
    for test in tests:
        try:
            files = verify(test)
            bundle = HibmsBundle(raw_dir(), test)
            try:
                result = evaluate(bundle)
            except ValueError as exc:  # scientific abstention: recorded, never hidden
                write_abstention(test, str(exc), files)
                bundle.close()
                print(f"ABSTAIN {test}: {exc}")
                continue
            records, s = result["records"], result["summary"]
            ref = nasa_reference(test)
            cam = bundle.camera_settings()
            rk = ref["reported_k_over_d0sq_per_s"]
            comparison = {
                "nasa_k_over_d0sq_per_s": rk,
                "vision_k_over_d0sq_per_s": s["k_over_d0sq_per_s"],
                "relative_difference": (s["k_over_d0sq_per_s"] / rk - 1) if rk else None,
                "nasa_dext_over_d0": ref["reported_dext_over_d0"],
                "implied_mm_per_px_from_nasa_d0": (ref["reported_d0_mm"] / s["d0_px"])
                if ref["reported_d0_mm"]
                else None,
                "implied_scale_note": "Consistency check only (NASA D0 / measured D0_px); never used to "
                "convert results to millimetres. NASA states droplet-size uncertainty +/-50 um.",
                "vision_regime_break_diameter_ratio_proxy": s["regime_break_diameter_ratio"],
                "note": "Scale-free comparison; no spatial calibration involved. NASA K has no per-value "
                "uncertainty in the source. Agreement is reported, not asserted.",
                "occlusion_assessment": occlusion_verdict(
                    s,
                    rk if isinstance(rk, float) else None,
                    bt if isinstance(bt := ref["reported_burn_time_s"], float) else None,
                ),
            }
            summary = {
                "test_point": test,
                "method": {
                    "method_id": HIBMS_DROPLET_CARD.method_id,
                    "version": HIBMS_DROPLET_CARD.version,
                    "status": HIBMS_DROPLET_CARD.status,
                },  # fmt: skip
                "evidence_eligibility": evidence_eligibility(ROOT),
                "reference_eligibility": reference_eligibility(ROOT),
                "camera": {
                    k: cam.get(k)
                    for k in (
                        "IPSU_TP_CAMERA",
                        "IPSU_TP_DIAG",
                        "IPSU_TP_FMT",
                        "IPSU_TP_FPS",
                        "IPSU_TP_XRES",
                        "IPSU_TP_YRES",
                    )
                },  # fmt: skip
                "physical_units": None,
                "physical_units_reason": "No mm/px scale in the PSI-69 calibration files (camera "
                "settings give "
                "resolution and frame rate only). Results stay in pixels or are scale-free (1/s).",
                "results": s,
                "uncertainty_budget": uncertainty_budget(s),
                "nasa_reference": ref,
                "comparison": comparison,
                "provenance": files,
                "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            out = OUT_DIR / test
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", "utf-8")
            with (out / "series.csv").open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=[f.name for f in fields(FrameRecord)], lineterminator="\n")
                w.writeheader()
                w.writerows(asdict(r) for r in records)
            (out / "d2_curve.svg").write_text(_svg(records, s, test), "utf-8")
            _overlay(bundle, records, out / "overlay.png")
            _evidence(bundle, records, s, out / "evidence.png")
            bundle.close()
            d = comparison["relative_difference"]
            diff_txt = f"{100 * d:+.1f}%" if isinstance(d, float) else "n/a"
            print(f"OK   {test}: K/D0^2 vision={s['k_over_d0sq_per_s']:.4f} NASA={rk} 1/s "
                  f"diff={diff_txt}  fit n={s['fit']['n']} R2={s['fit']['r_squared']:.3f}")  # fmt: skip
        except (ProvenanceError, ValueError, KeyError) as exc:
            failed = True
            print(f"FAIL {test}: {exc}", file=sys.stderr)
    write_evaluation()
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["fetch", "run"])
    p.add_argument("tests", nargs="+", help="FLEX identifiers, e.g. 20CAL10")
    a = p.parse_args(argv)
    if a.command == "fetch":
        fetch(a.tests)
        return 0
    return run(a.tests)


if __name__ == "__main__":
    raise SystemExit(main())
