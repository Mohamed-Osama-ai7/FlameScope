"""Rank fusion for hybrid retrieval: reciprocal-rank fusion (default) or weighted min-max fusion."""

from __future__ import annotations


def _ranked(scores: dict[int, float]) -> list[int]:
    return [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def rrf(
    score_maps: list[dict[int, float]], k: int = 60, weights: list[float] | None = None
) -> dict[int, float]:
    weights = weights or [1.0] * len(score_maps)
    fused: dict[int, float] = {}
    for sm, w in zip(score_maps, weights, strict=True):
        for rank, i in enumerate(_ranked(sm), 1):
            fused[i] = fused.get(i, 0.0) + w / (k + rank)
    return fused


def _minmax(sm: dict[int, float]) -> dict[int, float]:
    if not sm:
        return {}
    lo, hi = min(sm.values()), max(sm.values())
    span = hi - lo
    return {i: ((v - lo) / span if span > 0 else 1.0) for i, v in sm.items()}


def weighted(score_maps: list[dict[int, float]], weights: list[float]) -> dict[int, float]:
    fused: dict[int, float] = {}
    for sm, w in zip(score_maps, weights, strict=True):
        for i, v in _minmax(sm).items():
            fused[i] = fused.get(i, 0.0) + w * v
    return fused
