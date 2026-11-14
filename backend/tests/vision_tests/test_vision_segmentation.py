"""Segmentation accuracy on SYNTHETIC, TEST-ONLY frames (drawn shapes, never presented as data)."""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from app.vision.segmentation import SegmentationParams, segment_droplet  # noqa: E402

BG, DARK = 60000.0, 5000.0


def disk_frame(diameter_px: float, center=(64.0, 64.0), size=128, noise=0.0, seed=0):
    """Anti-aliased dark disk on a bright backlight, by 8x supersampling (synthetic test fixture)."""
    s = 8
    big = np.full((size * s, size * s), BG, np.float32)
    cv2.circle(
        big,
        (int(round(center[0] * s)), int(round(center[1] * s))),
        int(round(diameter_px / 2 * s)),
        DARK,
        -1,
        lineType=cv2.LINE_AA,
    )
    img = cv2.resize(big, (size, size), interpolation=cv2.INTER_AREA)
    if noise:
        img = img + np.random.default_rng(seed).normal(0, noise, img.shape).astype(np.float32)
    return img


@pytest.mark.parametrize("diameter", [8.0, 12.0, 16.5, 24.0, 32.0, 49.0])
def test_equivalent_diameter_within_half_pixel(diameter):
    det = segment_droplet(disk_frame(diameter))
    assert det is not None
    assert abs(det.equivalent_diameter_px - diameter) <= 0.5
    assert det.candidates == 1 and det.circularity > 0.7


def test_robust_to_sensor_noise():
    det = segment_droplet(disk_frame(20.0, noise=1500.0, seed=1))
    assert det is not None and abs(det.equivalent_diameter_px - 20.0) <= 0.6


def test_centroid_is_located():
    det = segment_droplet(disk_frame(14.0, center=(40.0, 90.0)))
    assert det is not None
    assert abs(det.centroid_x_px - 40.0) < 0.6 and abs(det.centroid_y_px - 90.0) < 0.6


def test_shapes_touching_the_border_are_ignored():
    img = disk_frame(14.0)
    img[:, :6] = DARK  # needle or igniter entering from the edge
    det = segment_droplet(img)
    assert det is not None and abs(det.equivalent_diameter_px - 14.0) <= 0.5


def test_elongated_and_irregular_shapes_are_rejected():
    img = np.full((128, 128), BG, np.float32)
    cv2.rectangle(img, (30, 60), (90, 66), DARK, -1)  # a fibre-like bar
    assert segment_droplet(img) is None


def test_empty_backlit_frame_gives_no_detection():
    assert segment_droplet(np.full((64, 64), BG, np.float32)) is None


def test_nearest_candidate_is_kept_when_tracking():
    img = disk_frame(10.0, center=(30.0, 30.0))
    other = disk_frame(20.0, center=(95.0, 95.0))
    both = np.minimum(img, other)
    assert segment_droplet(both).equivalent_diameter_px > 15  # largest without tracking
    tracked = segment_droplet(both, near=(31.0, 29.0))
    assert tracked is not None and tracked.equivalent_diameter_px < 15 and tracked.candidates == 2


def test_invalid_threshold_fraction_is_refused():
    with pytest.raises(ValueError):
        SegmentationParams(threshold_fraction=1.2)
    with pytest.raises(ValueError):
        segment_droplet(np.zeros((4, 4, 3), np.float32))
