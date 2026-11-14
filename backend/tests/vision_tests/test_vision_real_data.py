"""Real NASA data (skipped when the gitignored raw archives are absent) and the read-only API."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.vision.nasa_bundle import raw_dir

ROOT = Path(__file__).resolve().parents[3]
DERIVED = ROOT / "data" / "derived" / "flame_vision"
MANIFEST = ROOT / "data" / "metadata" / "vision_artifact_manifest.csv"
RAW_10 = raw_dir() / "PSI-69_Calibration_20CAL10A.zip"
client = TestClient(app)


def manifest_rows() -> list[dict[str, str]]:
    with MANIFEST.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_manifest_is_complete_and_licensed():
    rows = manifest_rows()
    tests = {"20CAL08", "20CAL10", "20CAL12", "30CAL02", "30CAL03", "30CAL06", "40CAL01"}
    assert {r["test_point"] for r in rows} == tests | {"DOCS", "NASA-TP"}
    for t in tests:  # every test bundle has its 4 files
        assert {r["role"] for r in rows if r["test_point"] == t} == {
            "test_log",
            "frame_index",
            "camera_settings",
            "frames_zip",
        }
    for r in rows:
        assert len(r["sha256"]) == 64
        if r["test_point"] == "NASA-TP":  # NTRS report: public use permitted, not CC0; registration pending
            assert r["license"] == "NTRS-PUBLIC-USE-PERMITTED" and r["source_id"] == "NASA-TP-2015-216046"
            assert (
                r["source_url"] == "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf"
            )
            continue
        assert r["license"] == "CC0-1.0"
        assert r["source_url"].startswith("https://psi.nasa.gov/geode-py/ws/studies/PSI-69/download?")
        assert r["relative_path"].startswith("data/raw/PSI-69/")


@pytest.mark.skipif(not RAW_10.exists(), reason="raw HIBMS archive not present (gitignored)")
def test_raw_archives_match_manifest():
    for r in manifest_rows():
        path = raw_dir() / r["file_name"]
        if path.exists():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"], r["file_name"]


@pytest.mark.skipif(not RAW_10.exists(), reason="raw HIBMS archive not present (gitignored)")
def test_evaluation_is_reproducible_on_nasa_frames():
    pytest.importorskip("cv2")
    from app.vision.metrology import evaluate
    from app.vision.nasa_bundle import HibmsBundle

    stored = json.loads((DERIVED / "20CAL10" / "summary.json").read_text("utf-8"))["results"]
    bundle = HibmsBundle(RAW_10.parent, "20CAL10")
    fresh = evaluate(bundle)["summary"]
    bundle.close()
    assert fresh["k_over_d0sq_per_s"] == pytest.approx(stored["k_over_d0sq_per_s"], rel=1e-12)
    assert fresh["frame_status_counts"] == stored["frame_status_counts"]
    assert fresh["frame_status_counts"]["unreadable_frame"] == 1  # 20CAL10A_01094.tif is truncated upstream


def test_stored_results_are_honest_about_units_and_validation():
    ev = json.loads((DERIVED / "evaluation.json").read_text("utf-8"))
    assert ev["n_tests"] == 7 and ev["n_computable"] == 3 and ev["n_abstained"] == 4
    assert ev["verdict"].startswith("not validated against the tabulated K")
    for t in ("20CAL10", "20CAL12", "30CAL03"):
        s = json.loads((DERIVED / t / "summary.json").read_text("utf-8"))
        assert s["physical_units"] is None and "mm" not in json.dumps(s["results"])
        assert s["results"]["fit"]["r_squared"] > 0.99 and s["results"]["fit_window_coverage"] == 1.0
        assert s["comparison"]["relative_difference"] < 0  # systematically below NASA, reported as is
        assert s["comparison"]["occlusion_assessment"]["verdict"] == "rejected_as_main_cause"
        assert s["results"]["post_break_slope_ratio"] < 0.1  # a real burning-to-evaporation break
        assert (DERIVED / t / "evidence.png").is_file()
    reasons = {
        "20CAL08": "no burning-to-evaporation break",  # disruption at ~5.3 s
        "30CAL02": "regime break",  # droplet leaves the view at 3.7 s, before extinction
        "30CAL06": "tracked in only",  # heptane: soot obscures the droplet
        "40CAL01": "tracked in only",  # droplet touches the image edge 4-6.5 s
    }
    for t, why in reasons.items():
        s = json.loads((DERIVED / t / "summary.json").read_text("utf-8"))
        assert s["computable"] is False and why in s["abstention_reason"], t


def test_api_routes():
    assert client.get("/api/v1/vision/method").json()["method_id"] == "vision.hibms_droplet_d2_pixel"
    ev = client.get("/api/v1/vision/evaluation").json()
    assert ev["n_computable"] == 3
    s = client.get("/api/v1/vision/tests/20CAL10").json()
    assert s["nasa_reference"]["run_id"] == "PSI-69-r002" and s["physical_units"] is None
    series = client.get("/api/v1/vision/tests/20CAL10/series").json()
    assert len(series) == 940 and {f["status"] for f in series} >= {"measured", "unreadable_frame"}
    assert client.get("/api/v1/vision/tests/30CAL06").json()["computable"] is False
    assert client.get("/api/v1/vision/tests/30CAL06/series").status_code == 404
    assert client.get("/api/v1/vision/tests/99CAL99").status_code == 404
    assert client.get("/api/v1/vision/tests/not-a-test").status_code == 422


NASA_TP_PDF = Path(
    os.environ.get("FLAMESCOPE_NASA_TP_PDF", "D:/FlameScope_raw/NASA-TP-2015-216046/20150023456.pdf")
)


def test_stored_crosscheck_is_consistent_and_honest_about_its_source():
    x = json.loads((DERIVED / "nasa_report_crosscheck.json").read_text("utf-8"))
    assert x["source"]["status"].startswith("UNREGISTERED")
    assert len(x["tests"]) == 3
    for t, r in x["tests"].items():
        lo, hi = r["ours_vs_published_range"]
        assert abs(r["ours_vs_published_curve"]) < 0.05, t  # vision agrees with NASA's published curve
        assert lo - 1e-9 <= r["ours_vs_published_curve"] <= hi + 1e-9
        assert abs(r["gap_decomposition"]["product"] - r["ours_vs_table_ratio"]) < 1e-9, t
        assert r["gap_decomposition"]["d0_definition"] < 0.95  # table D0 is the post-ignition diameter
        # the table D0 is the diameter of NASA's own plot at its t = 0, not the pre-ignition plateau
        assert r["published_d_mm_at_plot_t0"] == pytest.approx(r["table_d0_mm"], abs=0.02)
        assert r["published_plateau_d_mm"] > r["table_d0_mm"] + 0.08


@pytest.mark.skipif(not NASA_TP_PDF.exists(), reason="NASA/TP-2015-216046 PDF not present (kept outside git)")
def test_crosscheck_is_reproducible_from_the_pdf():
    pytest.importorskip("pypdfium2")
    import hashlib
    import importlib.util

    assert hashlib.sha256(NASA_TP_PDF.read_bytes()).hexdigest() == (
        "b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d"
    )
    spec = importlib.util.spec_from_file_location(
        "crosscheck", ROOT / "backend/scripts/nasa_report_crosscheck.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    stored = json.loads((DERIVED / "nasa_report_crosscheck.json").read_text("utf-8"))["tests"]["20CAL10"]
    summary = json.loads((DERIVED / "20CAL10" / "summary.json").read_text("utf-8"))
    fresh = mod.analyse("20CAL10", mod.FIGURES["20CAL10"], mod.render(NASA_TP_PDF, 36), summary)
    assert fresh["ours_vs_published_curve"] == pytest.approx(stored["ours_vs_published_curve"], abs=1e-9)
