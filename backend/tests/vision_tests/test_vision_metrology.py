"""Parsing of NASA bundle files, d^2 fitting, regime-break detection and abstention (no OpenCV needed)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.vision.metrology import FrameRecord, analyse, fit_line, regime_break
from app.vision.nasa_bundle import TestLog, parse_camera_settings, parse_frame_index, parse_test_log

# Verbatim excerpts of NASA PSI-69 calibration files for test point 20CAL10 (CC0-1.0).
LOG = """Test Point:\t\t\t\t20CAL10
Igniter On Time (milliseconds):\t\t1000
Burn to Completion (milliseconds):\t30000
AS Dispense Start:\t\t\t2009-03-05 19:20:00.047
AS Needles Retract:\t\t\t2009-03-05 19:20:06.561
AS Burn to Completion/Igniter On:\t2009-03-05 19:20:07.078
AS Igniter Off/Retract Start:\t\t2009-03-05 19:20:08.081
AS Retract Completed:\t\t\t2009-03-05 19:20:08.504
"""
INDEX = """Reference Time Stamp 3/5/2009 19:11:57.608521
Milliseconds 1596
ImgNum, DiskNum, FileNum, FileIndex, Mseconds, Delta,       Date,      MTimeStamp,       FileName
     0,       0,       0,         0, 69957908,    34, 03/05/2009, 19:25:57.908521, 20CAL10A_00000
     1,       1,       0,         0, 69957941,    33, 03/05/2009, 19:25:57.941854, 20CAL10A_00001
"""
SETTINGS = (
    '"IPSU1 TimeStamp","IPSU_TP_CAMERA(N/A)","IPSU_TP_DIAG(N/A)","IPSU_TP_FPS(N/A)","IPSU_TP_XRES(N/A)"\n'
    '"2009-03-05 19:20:07.5",SMD 1M60-20,HIBMS,30,512\n'
)


def test_parse_test_log_events_and_settings():
    log = parse_test_log(LOG)
    assert log.test_point == "20CAL10"
    assert log.event("AS Retract Completed") - log.event("AS Burn to Completion/Igniter On") == timedelta(
        seconds=1.426
    )
    assert log.settings_ms["Igniter On Time (milliseconds)"] == 1000
    with pytest.raises(KeyError):
        log.event("AS Nothing")
    with pytest.raises(ValueError):
        parse_test_log("no header here")


def test_parse_frame_index_and_camera_settings():
    idx = parse_frame_index(INDEX)
    assert list(idx) == ["20CAL10A_00000", "20CAL10A_00001"]
    assert (idx["20CAL10A_00001"] - idx["20CAL10A_00000"]).total_seconds() == pytest.approx(
        0.033333, abs=1e-6
    )
    cam = parse_camera_settings(SETTINGS)
    assert cam["IPSU_TP_DIAG"] == "HIBMS" and cam["IPSU_TP_FPS"] == "30" and cam["IPSU_TP_XRES"] == "512"


def test_fit_line_recovers_slope_with_interval():
    t = [i / 30 for i in range(60)]
    y = [1000 - 150 * a for a in t]
    f = fit_line(t, y)
    assert f.slope == pytest.approx(-150) and f.r_squared == pytest.approx(1.0)
    assert f.slope_ci95[0] <= f.slope <= f.slope_ci95[1]
    with pytest.raises(ValueError):
        fit_line([1.0, 2.0], [1.0, 2.0])


def test_regime_break_found_between_two_slopes():
    t = [i / 30 for i in range(300)]
    y = [1000 - 150 * a if a <= 6 else 100 - 5 * (a - 6) for a in t]
    assert regime_break(t, y, 2.0, 9.0) == pytest.approx(6.0, abs=0.05)


class FakeBundle:
    """Stands in for HibmsBundle in pure-analysis tests (only the event log is read)."""

    def test_log(self) -> TestLog:
        return parse_test_log(LOG)


def synthetic_records(k_px: float = 150.0, d0: float = 32.0, lost_after: float | None = None):
    """TEST-ONLY D(t): constant D0 before ignition, d^2-law burning, slow evaporation after 6 s."""
    recs = []
    t0 = datetime(2009, 3, 5, 19, 20, 7, 78000)
    for i in range(-15, 600):
        t = i / 30
        if 0.0 <= t <= 1.526:
            recs.append(FrameRecord(f"f{i}", t, "excluded_igniter_window"))
            continue
        if t < 0:
            d2 = d0**2
        elif t <= 6.0:
            d2 = d0**2 - k_px * t
        else:
            d2 = d0**2 - k_px * 6.0 - 5.0 * (t - 6.0)
        status, flags = "measured", ""
        if lost_after is not None and t > lost_after:
            flags = "diameter_jump"
        recs.append(FrameRecord(f"f{i}", t, status, diameter_px=max(d2, 1.0) ** 0.5, flags=flags))
    assert t0  # timestamps relative to the logged igniter-on event
    return recs


def test_analyse_recovers_normalised_rate_and_break():
    s = analyse(synthetic_records(), FakeBundle())  # type: ignore[arg-type]
    assert s["d0_px"] == pytest.approx(32.0)
    assert s["k_over_d0sq_per_s"] == pytest.approx(150.0 / 32.0**2, rel=0.01)
    assert s["regime_break_t_s"] == pytest.approx(6.0, abs=0.1)
    assert s["fit_window_coverage"] == pytest.approx(1.0)
    assert s["windows_s"]["fit"][0] == pytest.approx(1.526)


def test_analyse_abstains_when_droplet_is_lost():
    with pytest.raises(ValueError, match="too few measured frames|tracked in only"):
        analyse(synthetic_records(lost_after=2.0), FakeBundle())  # type: ignore[arg-type]


def test_analyse_abstains_without_free_droplet_before_ignition():
    recs = [r for r in synthetic_records() if r.t_s is not None and r.t_s >= 0]
    with pytest.raises(ValueError, match="free-droplet frames"):
        analyse(recs, FakeBundle())  # type: ignore[arg-type]


def test_analyse_abstains_without_a_burning_segment():
    with pytest.raises(ValueError, match="no d\\^2-law burning segment|regime break"):
        analyse(synthetic_records(k_px=-50.0), FakeBundle())  # type: ignore[arg-type]
