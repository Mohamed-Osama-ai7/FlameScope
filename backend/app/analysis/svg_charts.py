"""Minimal, dependency-free SVG scatter small-multiples (one panel per fuel).

Design rules (dataviz skill): one panel per fuel (never pooled), at most 3 categorical slots for
scatter (validated all-pairs set), shape as secondary encoding, legend always present for >= 2
groups, recessive grid, text in text tokens, native <title> hover tooltip on every point.
"""
from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from html import escape

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
AXIS = "#9a9893"
SLOTS = ("#2a78d6", "#eb6834", "#1baf7a")  # categorical slots 1-3 (blue, orange, aqua)
SHAPES = ("circle", "square", "triangle")


@dataclass
class Point:
    x: float
    y: float
    group: str
    tooltip: str


def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + (abs(lo) or 1.0)
    raw = (hi - lo) / target
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.5:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt(v: float) -> str:
    return f"{v:g}"


def _marker(shape: str, cx: float, cy: float, color: str, tip: str) -> str:
    ring = f'stroke="{SURFACE}" stroke-width="2"'
    t = f"<title>{escape(tip)}</title>"
    if shape == "square":
        return f'<rect x="{cx-4.5:.1f}" y="{cy-4.5:.1f}" width="9" height="9" rx="1.5" fill="{color}" {ring}>{t}</rect>'
    if shape == "triangle":
        pts = f"{cx:.1f},{cy-5.5:.1f} {cx+5.2:.1f},{cy+4:.1f} {cx-5.2:.1f},{cy+4:.1f}"
        return f'<polygon points="{pts}" fill="{color}" {ring}>{t}</polygon>'
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}" {ring}>{t}</circle>'


def scatter_by_fuel(
    title: str,
    subtitle: str,
    xlabel: str,
    ylabel: str,
    panels: dict[str, list[Point]],
    groups: list[str],
    footnote: str,
) -> str:
    if len(groups) > len(SLOTS):
        raise ValueError("scatter charts are capped at 3 categorical groups")
    sub_lines = textwrap.wrap(subtitle, width=135) or [""]
    extra = 16 * (len(sub_lines) - 1)  # push legend and plots down for wrapped subtitle lines
    foot_lines = textwrap.wrap(footnote, width=150) or [""]
    width, height = 980, 470 + extra + 14 * (len(foot_lines) - 1)
    left, right, top, bottom, gap = 70, 20, 112 + extra, 70 + 14 * (len(foot_lines) - 1), 50
    legend_y = 72 + extra
    pw = (width - left - right - gap * (len(panels) - 1)) / max(len(panels), 1)
    ph = height - top - bottom
    allp = [p for pts in panels.values() for p in pts]
    xs = [p.x for p in allp] or [0.0, 1.0]
    ys = [p.y for p in allp] or [0.0, 1.0]
    xt, yt = nice_ticks(min(xs), max(xs)), nice_ticks(min(0.0, min(ys)), max(ys))
    x0, x1, y0, y1 = xt[0], xt[-1], yt[0], yt[-1]

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" font-family="Inter, Segoe UI, system-ui, sans-serif" role="img" '
        f'aria-label="{escape(title)}">',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        f'<text x="{left}" y="28" font-size="17" font-weight="600" fill="{TEXT_PRIMARY}">{escape(title)}</text>',
    ]
    for li, line in enumerate(sub_lines):
        out.append(f'<text x="{left}" y="{49 + 16 * li}" font-size="12.5" fill="{TEXT_SECONDARY}">{escape(line)}</text>')
    lx: float = left
    for i, g in enumerate(groups):
        out.append(_marker(SHAPES[i], lx + 5, legend_y, SLOTS[i], g))
        out.append(f'<text x="{lx+15}" y="{legend_y + 4}" font-size="12" fill="{TEXT_SECONDARY}">{escape(g)}</text>')
        lx += 22 + 7.2 * len(g) + 18
    for pi, (fuel, pts) in enumerate(panels.items()):
        ox = left + pi * (pw + gap)

        def sx(v: float, ox: float = ox) -> float:
            return ox + (v - x0) / (x1 - x0) * pw

        def sy(v: float) -> float:
            return top + ph - (v - y0) / (y1 - y0) * ph

        out.append(f'<text x="{ox}" y="{top-10}" font-size="13" font-weight="600" fill="{TEXT_PRIMARY}">'
                   f'{escape(fuel)} (n = {len(pts)})</text>')
        for v in yt:
            out.append(f'<line x1="{ox}" x2="{ox+pw}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
            if pi == 0:
                out.append(f'<text x="{ox-8}" y="{sy(v)+4:.1f}" font-size="11" text-anchor="end" fill="{TEXT_SECONDARY}">{_fmt(v)}</text>')
        for v in xt:
            out.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top+ph}" y2="{top+ph+4}" stroke="{AXIS}"/>')
            out.append(f'<text x="{sx(v):.1f}" y="{top+ph+18}" font-size="11" text-anchor="middle" fill="{TEXT_SECONDARY}">{_fmt(v)}</text>')
        out.append(f'<line x1="{ox}" x2="{ox+pw}" y1="{top+ph}" y2="{top+ph}" stroke="{AXIS}"/>')
        out.append(f'<text x="{ox+pw/2:.1f}" y="{top+ph+40}" font-size="12" text-anchor="middle" fill="{TEXT_PRIMARY}">{escape(xlabel)}</text>')
        for p in sorted(pts, key=lambda p: groups.index(p.group)):
            gi = groups.index(p.group)
            out.append(_marker(SHAPES[gi], sx(p.x), sy(p.y), SLOTS[gi], p.tooltip))
    out.append(f'<text transform="translate(18 {top+ph/2:.0f}) rotate(-90)" font-size="12" text-anchor="middle" fill="{TEXT_PRIMARY}">{escape(ylabel)}</text>')
    for fi, line in enumerate(foot_lines):
        y = height - 10 - 14 * (len(foot_lines) - 1 - fi)
        out.append(f'<text x="{left}" y="{y}" font-size="11" fill="{TEXT_SECONDARY}">{escape(line)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
