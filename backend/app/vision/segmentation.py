"""Droplet segmentation for backlit (shadowgraph) frames: the droplet is a dark, compact, round blob.

Method (classical, deterministic):
1. background level = median grey level of the frame (backlight dominates the field of view);
2. dark mask = pixels below ``threshold_fraction`` x background (0.5 = half-intensity edge);
3. external contours; reject candidates touching the image border (needles, igniters, injector arms
   enter from the edges), elongated candidates and non-round candidates;
4. keep the candidate nearest to ``near`` (the tracked droplet position) when given, otherwise the
   largest; area = filled external-contour pixel count (a bright refraction spot cannot shrink it).

Pixel-domain only: ``equivalent_diameter_px = 2 sqrt(area / pi)``. Converting to millimetres needs a
documented spatial calibration, which this module does not invent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SegmentationParams:
    threshold_fraction: float = 0.5
    min_area_px: float = 6.0
    max_aspect_ratio: float = 1.3
    min_circularity: float = 0.7  # 4*pi*A/P^2; discrete perimeters push small blobs above 1
    border_margin_px: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold_fraction < 1.0:
            raise ValueError("threshold_fraction must be in (0, 1)")


@dataclass(frozen=True)
class DropletDetection:
    area_px: float
    equivalent_diameter_px: float
    centroid_x_px: float
    centroid_y_px: float
    circularity: float
    bbox: tuple[int, int, int, int]
    background_level: float
    candidates: int  # qualifying candidates before choosing the largest (>1 is flagged downstream)


def segment_droplet(
    image: Any, params: SegmentationParams | None = None, near: tuple[float, float] | None = None
) -> DropletDetection | None:
    """Return the droplet detection for one frame, or None when no qualifying droplet is visible."""
    import cv2
    import numpy as np

    p = params or SegmentationParams()
    img = np.asarray(image, dtype=np.float32)
    if img.ndim != 2:
        raise ValueError("expected a single-channel (grey) frame")
    background = float(np.median(img))
    if background <= 0:
        return None
    mask = (img < p.threshold_fraction * background).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    h_img, w_img = img.shape
    m = p.border_margin_px
    kept: list[tuple[float, Any, float, float, float]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if x < m or y < m or x + w > w_img - m or y + h > h_img - m:
            continue
        # Pixel count of the filled contour: unbiased at the half-intensity edge, holes filled.
        # (cv2.contourArea runs through boundary-pixel centres and loses ~half a pixel ring.)
        filled = np.zeros((h, w), np.uint8)
        cv2.drawContours(filled, [c - (x, y)], -1, 1, thickness=cv2.FILLED)
        area = float(filled.sum())
        if area < p.min_area_px or max(w / h, h / w) > p.max_aspect_ratio:
            continue
        perimeter = float(cv2.arcLength(c, True))
        polygon_area = float(cv2.contourArea(c))
        circularity = 4.0 * math.pi * polygon_area / perimeter**2 if perimeter > 0 else 0.0
        if circularity < p.min_circularity:
            continue
        mom = cv2.moments(c)
        if mom["m00"] <= 0:
            continue
        kept.append((area, c, circularity, mom["m10"] / mom["m00"], mom["m01"] / mom["m00"]))
    if not kept:
        return None
    if near is None:
        area, contour, circularity, cx, cy = max(kept, key=lambda k: k[0])
    else:
        area, contour, circularity, cx, cy = min(
            kept, key=lambda k: math.hypot(k[3] - near[0], k[4] - near[1])
        )
    x, y, w, h = cv2.boundingRect(contour)
    return DropletDetection(
        area_px=area,
        equivalent_diameter_px=2.0 * math.sqrt(area / math.pi),
        centroid_x_px=cx,
        centroid_y_px=cy,
        circularity=circularity,
        bbox=(int(x), int(y), int(w), int(h)),
        background_level=background,
        candidates=len(kept),
    )
