"""Physics-informed analysis endpoints (read-only; PSI-69 reported values via the verified loader)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.analysis import flex_run_level as fx
from app.analysis import physics
from app.data_platform.settings import project_root
from app.domain.eligibility import EligibilityPolicy

PROJECT_ROOT = project_root()
DEXT_ORIGIN_NOT_USED = "not_used_unregistered_caption_source"
router = APIRouter(prefix="/physics", tags=["physics"])
Fuel = Literal["Methanol", "Heptane"]


@lru_cache(maxsize=1)
def _runs() -> tuple[fx.FlexRun, ...]:
    man = PROJECT_ROOT / "data/metadata/artifact_manifest.csv"
    # central evidence policy: registry status AND the scientific decision (source_eligibility.csv)
    decision = EligibilityPolicy(PROJECT_ROOT).decision("PSI-69")
    if not decision.usable_as_evidence:
        raise RuntimeError(f"PSI-69 is {decision.eligibility.value}: {decision.reason}")
    entry = fx.manifest_entry(man)
    runs, _ = fx.load_verified(PROJECT_ROOT / entry["relative_path"], man)  # SHA-256 checked
    fx.attach_enrichment(runs, PROJECT_ROOT / "data/derived/flex_enrichment_v1.csv")
    for r in runs:
        # dext_origin is derived from NASA/TP-2015-216046 caption notes (unregistered source); physics
        # never uses it, and it is blanked here so no future calculation can read it by accident.
        r.dext_origin = DEXT_ORIGIN_NOT_USED
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
