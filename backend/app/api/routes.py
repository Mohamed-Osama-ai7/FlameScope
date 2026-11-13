from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.domain.comparison import ComparisonRequest, ComparisonResult, validate_comparison
from app.domain.regimes import REGIME_DESCRIPTIONS, REGIME_VARIABLES, CombustionRegime
from app.domain.sources import (
    RegistryError,
    SourceRecord,
    find_source,
    load_registry,
    official_resource_recorded,
)
from app.science.droplet import BurningRateResult, DropletSeries, fit_burning_rate_constant
from app.science.method_cards import METHOD_REGISTRY, MethodCard

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = PROJECT_ROOT / "data" / "metadata" / "source_registry.csv"


def _registry() -> list[SourceRecord]:
    try:
        return load_registry(REGISTRY_PATH)
    except RegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:  # pydantic validation of a malformed row
        raise HTTPException(status_code=500, detail=f"Invalid source registry: {exc}") from exc


@router.get("/sources", tags=["sources"], response_model=list[SourceRecord])
def list_sources() -> list[SourceRecord]:
    """Return the source registry; rows are metadata, not proof of scientific validation."""
    return _registry()


@router.get("/status", tags=["system"])
def project_status() -> dict[str, object]:
    records = _registry()
    return {
        "project": "FlameScope",
        "team": "UnderFitted",
        "official_challenge_resource_recorded": official_resource_recorded(records),
        # No measurement store exists yet; flip only when the ingestion pipeline loads verified rows.
        "scientific_dataset_loaded": False,
        "sources_usable_as_evidence": [r.source_id for r in records if r.usable_as_evidence],
        "notice": "No scientific measurements are seeded in this starter scaffold.",
    }


@router.get("/regimes", tags=["science"])
def list_regimes() -> list[dict[str, object]]:
    return [
        {
            "regime": r.value,
            "description": REGIME_DESCRIPTIONS[r],
            "variables": sorted(REGIME_VARIABLES[r]),
        }
        for r in CombustionRegime
    ]


@router.post("/comparisons/validate", tags=["science"], response_model=ComparisonResult)
def compare(request: ComparisonRequest) -> ComparisonResult:
    return validate_comparison(request.a, request.b)


@router.get("/methods", tags=["science"], response_model=list[MethodCard])
def list_methods() -> list[MethodCard]:
    return list(METHOD_REGISTRY.values())


@router.post(
    "/analysis/droplet/burning-rate-constant",
    tags=["science"],
    response_model=BurningRateResult,
)
def burning_rate_constant(series: DropletSeries) -> BurningRateResult:
    """d^2-law fit. Returns computable=false with a reason instead of guessing.

    Registered sources must be ACQUIRED/VERIFIED; candidate or QUARANTINED sources (e.g. PSI-98)
    are refused. Unregistered source ids are computed but flagged as not traceable.
    """
    source = find_source(_registry(), series.provenance.source_id)
    if source is not None and not source.usable_as_evidence:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Source {source.source_id} has status {source.verification_status.value} and "
                "cannot be used for scientific analysis until acquired/verified."
            ),
        )
    result = fit_burning_rate_constant(series)
    if source is None:
        result.warnings.append(
            f"source_id '{series.provenance.source_id}' is not in the source registry; "
            "result is not traceable to a registered NASA artifact"
        )
    return result
