"""Method card for the HIBMS droplet vision method (same contract as app.science.method_cards)."""

from __future__ import annotations

from app.domain.regimes import CombustionRegime
from app.science.method_cards import MethodCard, Reference, VariableSpec
from app.vision.metrology import METHOD_ID, METHOD_VERSION

HIBMS_DROPLET_CARD = MethodCard(
    method_id=METHOD_ID,
    version=METHOD_VERSION,
    title="Backlit droplet diameter (pixels) and scale-free d^2-law rate from FLEX HIBMS frames",
    regimes=[CombustionRegime.FLEX_DROPLET],
    formula=(
        "D_px = 2 sqrt(A_px / pi) per frame (A_px = filled dark-blob area at threshold f x background); "
        "D_px^2(t) = D_px,0^2 - K_px t over the a-priori fit window; K/D0^2 = K_px / D_px,0^2  [1/s]"
    ),
    variables=[
        VariableSpec(symbol="D_px", name="droplet equivalent diameter", unit="px", role="output"),
        VariableSpec(symbol="K_px", name="d^2 slope in image units", unit="px^2/s", role="output"),
        VariableSpec(symbol="K/D0^2", name="normalised burning rate (scale-free)", unit="1/s", role="output"),
        VariableSpec(symbol="f", name="threshold fraction of background", unit="1", role="parameter"),
        VariableSpec(symbol="t", name="frame time from NASA frame index", unit="s", role="input"),
    ],
    references=[
        Reference(
            citation="NASA PSI-69 FLEX, Calibration folder (HIBMS frames, frame index, test log)",
            doi="10.60555/mbq8-0451",
        ),
        Reference(
            citation="Yu F, Shaw BD (2014) Interpretation of backlit droplet images from ISS droplet "
            "combustion experiments",
            doi="10.2478/gsr-2014-0007",
        ),
        Reference(
            citation="Shaw BD (2014) ISS droplet combustion experiments - uncertainties in droplet "
            "sizes and burning rates",
            doi="10.1007/s12217-014-9377-x",
        ),
    ],  # fmt: skip
    assumptions=[
        "Backlit frame: the droplet is the largest dark, round blob not touching the image border.",
        "Half-intensity threshold approximates the droplet edge; sensitivity reported at f = 0.4/0.5/0.6.",
        "Spherical droplet: diameter from area; no depth or defocus correction.",
        "Timestamps from NASA's per-frame index; t = 0 at the logged igniter-on event.",
    ],
    validity_limits=[
        "Pixel domain only: no documented mm/px scale exists in the PSI calibration files, so no mm values.",
        "The HIBMS view does not show the flame; the regime break is a droplet-side proxy, not flame "
        "extinction.",
        "Frames with igniters in view are excluded, so the earliest burning (fastest for methanol) is "
        "unseen.",
        "Disruption tests violate the d^2-law near the end; the break may mark disruption, not extinction.",
    ],
    required_inputs=["HIBMS frames zip", "frame index <T>A.txt", "test-point event log <T>.txt"],
    uncertainty_method=(
        "1-sigma relative: OLS slope standard error combined with D0 frame-to-frame dispersion (1.4826 MAD); "
        "threshold sensitivity reported separately; segmentation bias <= 0.35 px on synthetic disks."
    ),
    validation=[
        "Unit tests on synthetic test-only disks of known diameter (8-32 px): |error| <= 0.5 px.",
        "Scale-free comparison of K/D0^2 with NASA-reported K and D0 for the same FLEX test (PSI-69 table).",
    ],
    abstention_conditions=[
        "fewer than 3 free-droplet frames before igniter-on",
        "fewer than 20 measured frames after the igniters leave the field of view",
        "fit window shorter than 10 frames",
    ],
    status="implemented_compared_with_nasa_reported_values_not_validated",
)
