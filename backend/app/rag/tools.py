"""Whitelisted numerical tools. The LLM may REQUEST a tool; arguments are validated with pydantic and the
result comes from the existing, tested backend code. The LLM never produces a number that is not in a
cited chunk or a tool result (see citations.py)."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.analysis import flex_run_level as fx
from app.domain.comparison import ComparisonRequest, validate_comparison
from app.domain.sources import find_source, load_registry
from app.rag.config import PROJECT_ROOT
from app.rag.measurements import MeasurementFact
from app.science.droplet import DropletSeries, fit_burning_rate_constant
from app.science.method_cards import METHOD_REGISTRY


class ToolResult(BaseModel):
    tool_result_id: str
    tool: str
    ok: bool
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None


class GetFlexRunArgs(BaseModel):
    experiment_id: str = Field(min_length=1, description="FLEX-070, identifier 193F001, or 'PSI-69 row 70'")
    variable: str | None = Field(
        default=None,
        description="optional platform variable, e.g. ambient_pressure, extinction_diameter, burn_time",
    )


class FlexSummaryArgs(BaseModel):
    fuel: str = Field(pattern="^(Methanol|Heptane)$")


class NoArgs(BaseModel):
    pass


@lru_cache(maxsize=1)
def _flex(root: Path = PROJECT_ROOT) -> tuple[list[fx.FlexRun], list[MeasurementFact]]:
    from app.rag.ingest import load_flex  # local import: ingest imports nothing from tools

    runs, _, facts = load_flex(root)
    return runs, facts


def _runs() -> list[fx.FlexRun]:
    return _flex()[0]


def match_runs(experiment_id: str) -> list[fx.FlexRun]:
    key = experiment_id.strip().lower()
    return [
        r
        for r in _runs()
        if key
        in {
            r.identifier.lower(),
            f"flex-{r.flex_test_number:03d}",
            f"psi-69 row {r.psi_row}",
            f"psi-69-r{r.psi_row:03d}",
        }
    ]


def get_flex_run(a: GetFlexRunArgs) -> dict[str, Any]:
    """Measurements of one PSI-69 run with evidence status, flags and platform provenance ids.

    A value is returned only when it may be stated (CLEAN or QUALIFIED); missing and invalid cells come
    back with value null and their flags, so no caller can mistake them for measurements.
    """
    matches = match_runs(a.experiment_id)
    if not matches:
        raise LookupError(f"no PSI-69 record matches '{a.experiment_id}'")
    facts = _flex()[1]
    return {
        "value_origin": "reported_in_source (PSI-69 experimental table); nothing is calculated or imputed",
        "source_eligibility": "PSI-69 PENDING_VERIFICATION (see /api/v1/rag/sources)",
        "ambiguous_identifier": len(matches) > 1,
        "records": [
            {
                "run_id": f"PSI-69-r{r.psi_row:03d}",
                "flex_test": r.flex_test_number,
                "psi_row": r.psi_row,
                "identifier": r.identifier,
                "fuel": r.fuel,
                "test_end": r.test_end,
                "row_flags": list(r.row_flags),
                "measurements": [
                    f.public()
                    for f in facts
                    if f.psi_row == r.psi_row and (not a.variable or f.variable == a.variable)
                ],
            }
            for r in matches
        ],
    }


def flex_summary(a: FlexSummaryArgs) -> dict[str, Any]:
    path = PROJECT_ROOT / "reports/flex_run_level_v0.2/summary.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    return {
        "provenance": "approved FLEX run-level analysis v0.2.0 (reports/flex_run_level_v0.2/summary.json), "
        "returned as published",
        "analysis_version": d["analysis_version"],
        "value_origin": d["value_origin"],
        "descriptive_exploratory_only": True,
        "fuel": a.fuel,
        "descriptive_by_fuel": d["descriptive_by_fuel"][a.fuel],
    }


def compare(a: ComparisonRequest) -> dict[str, Any]:
    return validate_comparison(a.a, a.b).model_dump(mode="json")


def fit_k(a: DropletSeries) -> dict[str, Any]:
    src = find_source(
        load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv"), a.provenance.source_id
    )
    if src is not None and not src.usable_as_evidence:  # same gate as POST /analysis/droplet/...
        raise ValueError(f"source {src.source_id} is {src.verification_status.value}; refusing to analyse")
    return fit_burning_rate_constant(a).model_dump(mode="json")


def list_methods(_: NoArgs) -> dict[str, Any]:
    return {
        "methods": [
            {"method_id": m.method_id, "title": m.title, "status": m.status} for m in METHOD_REGISTRY.values()
        ]
    }


TOOLS: dict[str, tuple[type[BaseModel], Callable[[Any], dict[str, Any]]]] = {
    "get_flex_run": (GetFlexRunArgs, get_flex_run),
    "flex_summary": (FlexSummaryArgs, flex_summary),
    "validate_comparison": (ComparisonRequest, compare),
    "fit_burning_rate_constant": (DropletSeries, fit_k),
    "list_methods": (NoArgs, list_methods),
}


def tool_catalog() -> list[dict[str, Any]]:
    return [{"name": n, "arguments_schema": m.model_json_schema()} for n, (m, _) in TOOLS.items()]


def run_tool(call_id: str, name: str, arguments: dict[str, Any]) -> ToolResult:
    if name not in TOOLS:
        return ToolResult(
            tool_result_id=call_id, tool=name, ok=False, error=f"tool '{name}' is not whitelisted"
        )
    model, fn = TOOLS[name]
    try:
        args = model.model_validate(arguments)
    except ValidationError as exc:
        return ToolResult(
            tool_result_id=call_id,
            tool=name,
            ok=False,
            arguments=arguments,
            error=f"invalid arguments: {exc.errors(include_url=False)[:3]}",
        )
    try:
        return ToolResult(tool_result_id=call_id, tool=name, ok=True, arguments=arguments, result=fn(args))
    except (LookupError, ValueError) as exc:
        return ToolResult(tool_result_id=call_id, tool=name, ok=False, arguments=arguments, error=str(exc))
