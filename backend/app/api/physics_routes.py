"""Physics-informed analysis endpoints (read-only; PSI-69 reported values via the verified loader)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.analysis import flex_run_level as fx
from app.analysis import physics
from app.domain.sources import load_registry

PROJECT_ROOT = Path(__file__).resolve().parents[3]
router = APIRouter(prefix="/physics", tags=["physics"])
Fuel = Literal["Methanol", "Heptane"]


@lru_cache(maxsize=1)
def _runs() -> tuple[fx.FlexRun, ...]:
    man = PROJECT_ROOT / "data/metadata/artifact_manifest.csv"
    reg = {r.source_id: r for r in load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv")}
    if "PSI-69" not in reg or not reg["PSI-69"].usable_as_evidence:
        raise RuntimeError("PSI-69 is not ACQUIRED/VERIFIED in the source registry")
    entry = fx.manifest_entry(man)
    runs, _ = fx.load_verified(PROJECT_ROOT / entry["relative_path"], man)  # SHA-256 checked
    fx.attach_enrichment(runs, PROJECT_ROOT / "data/derived/flex_enrichment_v1.csv")
    return tuple(runs)


def _data() -> list[fx.FlexRun]:
    try:
        return list(_runs())
    except (FileNotFoundError, fx.IntegrityError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=f"PSI-69 data unavailable: {exc}") from exc


@router.get("/d2-consistency")
def d2_consistency(
    fuel: Fuel | None = None,
    diameter_halfwidth_mm: float | None = Query(
        default=None, gt=0, le=1.0, description="optional diameter bound added to the resolution interval"
    ),
) -> dict[str, Any]:
    """Internal consistency of reported D0, Dext, K and burn time with the d^2-law (diagnostic)."""
    return physics.d2_consistency(_data(), fuel, diameter_halfwidth_mm)


@router.get("/oxygen-effect")
def oxygen_effect(fuel: Fuel | None = None) -> dict[str, Any]:
    """Within-stratum association of ambient O2 mole fraction with reported K (OLS, HC3)."""
    return physics.oxygen_effect(_data(), fuel)
