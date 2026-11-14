"""Read-only API for Flame Vision & Metrology results (mounted under /api/v1).

Serves the outputs written by ``backend/scripts/run_flame_vision.py run`` from
data/derived/flame_vision/. Image processing never runs inside a request, so the API needs neither
OpenCV nor the raw NASA archives.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from app.data_platform.settings import project_root
from app.science.method_cards import MethodCard
from app.vision.method_card import HIBMS_DROPLET_CARD

router = APIRouter(prefix="/vision", tags=["flame vision"])
TEST_POINT = r"^\d{2}CAL\d{2}$"  # FLEX calibration test identifiers, e.g. 20CAL10 (also blocks path tricks)


class FrameOut(BaseModel):
    frame: str
    t_s: float | None
    status: str
    diameter_px: float | None
    area_px: float | None
    circularity: float | None
    centroid_x_px: float | None
    centroid_y_px: float | None
    candidates: int | None
    flags: list[str]


def _out_dir() -> Path:
    return project_root() / "data" / "derived" / "flame_vision"


def _read_json(path: Path, what: str) -> dict[str, Any]:
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"{what} not found; run backend/scripts/run_flame_vision.py"
        )
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


def _num(v: str) -> float | None:
    return float(v) if v not in ("", "None") else None


@router.get("/method", response_model=MethodCard)
def vision_method() -> MethodCard:
    return HIBMS_DROPLET_CARD


@router.get("/evaluation")
def vision_evaluation() -> dict[str, Any]:
    """Cross-test comparison of the scale-free K/D0^2 with NASA's reported values, including abstentions."""
    return _read_json(_out_dir() / "evaluation.json", "evaluation")


@router.get("/tests/{test_point}")
def vision_test(test_point: str = PathParam(pattern=TEST_POINT)) -> dict[str, Any]:
    """Full summary for one test: results, NASA reference, comparison, provenance (or abstention)."""
    return _read_json(_out_dir() / test_point / "summary.json", f"vision result for {test_point}")


@router.get("/tests/{test_point}/series", response_model=list[FrameOut])
def vision_series(test_point: str = PathParam(pattern=TEST_POINT)) -> list[FrameOut]:
    """Per-frame records (pixels): measured, excluded and unreadable frames are all listed with a status."""
    path = _out_dir() / test_point / "series.csv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no frame series for {test_point} (absent or abstained)")
    with path.open(encoding="utf-8", newline="") as fh:
        return [
            FrameOut(
                frame=r["frame"],
                t_s=_num(r["t_s"]),
                status=r["status"],
                diameter_px=_num(r["diameter_px"]),
                area_px=_num(r["area_px"]),
                circularity=_num(r["circularity"]),
                centroid_x_px=_num(r["centroid_x_px"]),
                centroid_y_px=_num(r["centroid_y_px"]),
                candidates=int(r["candidates"]) if r["candidates"] not in ("", "None") else None,
                flags=[f for f in r["flags"].split(";") if f],
            )
            for r in csv.DictReader(fh)
        ]
