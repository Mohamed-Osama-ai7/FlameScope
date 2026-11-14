"""Flame Vision & Metrology (first validated module): FLEX HIBMS backlit droplet images.

Scope (docs/16_flame_vision_metrology.md):
* Input: NASA PSI-69 "Calibration" test bundles (HIBMS backlit droplet frames as 16-bit TIFF inside the
  PSI zip, the per-frame timestamp index, the test-point event log). Archives are read in place, never
  extracted or modified.
* Output: droplet diameter in PIXELS per frame, the d^2(t) slope in px^2/s, and the scale-free
  normalised burning rate K/D0^2 in 1/s, which can be compared with NASA's reported K/D0^2 without any
  spatial calibration. No millimetre value is produced: the PSI calibration files document resolution
  (512 x 512) and frame rate (30 fps) but no pixel scale.
* Classical image processing only (threshold + contours); no trained model.
"""
