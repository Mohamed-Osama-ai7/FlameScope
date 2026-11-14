"""Real NASA data (skipped when the gitignored raw archives are absent) and the read-only API."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[3]
DERIVED = ROOT / "data" / "derived" / "flame_vision"
MANIFEST = ROOT / "data" / "metadata" / "vision_artifact_manifest.csv"
RAW_10 = ROOT / "data/raw/PSI-69/calibration/PSI-69_Calibration_20CAL10A.zip"
client = TestClient(app)


def manifest_rows() -> list[dict[str, str]]:
    with MANIFEST.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_manifest_is_complete_and_licensed():
    rows = manifest_rows()
    assert {r["test_point"] for r in rows} == {"20CAL10", "20CAL12", "30CAL06"}
    for r in rows:
        assert len(r["sha256"]) == 64 and r["license"] == "CC0-1.0"
        assert r["source_url"].startswith("https://psi.nasa.gov/geode-py/ws/studies/PSI-69/download?")
        assert r["relative_path"].startswith("data/raw/PSI-69/calibration/")


@pytest.mark.skipif(not RAW_10.exists(), reason="raw HIBMS archive not present (gitignored)")
def test_raw_archives_match_manifest():
    for r in manifest_rows():
        path = ROOT / r["relative_path"]
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
    assert ev["n_tests"] == 3 and ev["n_computable"] == 2 and ev["n_abstained"] == 1
    assert ev["verdict"].startswith("not validated")
    for t in ("20CAL10", "20CAL12"):
        s = json.loads((DERIVED / t / "summary.json").read_text("utf-8"))
        assert s["physical_units"] is None and "mm" not in json.dumps(s["results"])
        assert s["results"]["fit"]["r_squared"] > 0.99 and s["results"]["fit_window_coverage"] == 1.0
        assert s["comparison"]["relative_difference"] < 0  # systematically below NASA, reported as is
    heptane = json.loads((DERIVED / "30CAL06" / "summary.json").read_text("utf-8"))
    assert heptane["computable"] is False and heptane["abstention_reason"]


def test_api_routes():
    assert client.get("/api/v1/vision/method").json()["method_id"] == "vision.hibms_droplet_d2_pixel"
    ev = client.get("/api/v1/vision/evaluation").json()
    assert ev["n_computable"] == 2
    s = client.get("/api/v1/vision/tests/20CAL10").json()
    assert s["nasa_reference"]["run_id"] == "PSI-69-r002" and s["physical_units"] is None
    series = client.get("/api/v1/vision/tests/20CAL10/series").json()
    assert len(series) == 940 and {f["status"] for f in series} >= {"measured", "unreadable_frame"}
    assert client.get("/api/v1/vision/tests/30CAL06").json()["computable"] is False
    assert client.get("/api/v1/vision/tests/30CAL06/series").status_code == 404
    assert client.get("/api/v1/vision/tests/99CAL99").status_code == 404
    assert client.get("/api/v1/vision/tests/not-a-test").status_code == 422
