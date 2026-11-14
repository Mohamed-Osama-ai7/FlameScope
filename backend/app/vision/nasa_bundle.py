"""Read a NASA PSI-69 FLEX calibration test bundle without modifying it.

Files per test point ``<T>`` (all published by PSI under ``PSI-69/Calibration``):
* ``PSI-69_Calibration_<T>.txt``                    test-point event log ("AS ...:  <timestamp>")
* ``PSI-69_Calibration_<T>A.txt``                   HIBMS frame index (frame name -> timestamp)
* ``PSI-69_Calibration_<T>_HIBMS_Camera_Settings.txt``  camera, bit depth, fps, resolution
* ``PSI-69_Calibration_<T>A.zip``                   HIBMS frames, 16-bit TIFF (read in place)
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_EVENT = re.compile(r"^(AS [^:]+):\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s*$")
_SETTING = re.compile(r"^([A-Za-z ]+\(milliseconds\)):\s*(\d+)\s*$")
TEXT_ENCODING = "latin-1"  # PSI calibration text files are plain ASCII; latin-1 never fails
RAW_DIR_ENV = "FLAMESCOPE_VISION_RAW_DIR"


def raw_dir() -> Path:
    """Physical folder of the PSI-69 calibration files (kept outside git, e.g. on another drive).

    ``FLAMESCOPE_VISION_RAW_DIR`` overrides the default ``<repo>/data/raw/PSI-69/calibration``. The
    manifest's ``relative_path`` is the logical project location; files are resolved by ``file_name``.
    """
    value = os.environ.get(RAW_DIR_ENV, "").strip()
    if value:
        return Path(value)
    return Path(__file__).resolve().parents[3] / "data" / "raw" / "PSI-69" / "calibration"


@dataclass(frozen=True)
class TestLog:
    test_point: str
    events: dict[str, datetime]
    settings_ms: dict[str, int]

    def event(self, name: str) -> datetime:
        if name not in self.events:
            raise KeyError(f"event '{name}' not in test log {self.test_point}")
        return self.events[name]


def parse_test_log(text: str) -> TestLog:
    test_point = ""
    events: dict[str, datetime] = {}
    settings: dict[str, int] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Test Point:"):
            test_point = line.split(":", 1)[1].strip()
        elif m := _EVENT.match(line):
            events[m.group(1).strip()] = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S.%f")
        elif m := _SETTING.match(line):
            settings[m.group(1).strip()] = int(m.group(2))
    if not test_point:
        raise ValueError("not a FLEX test-point log: 'Test Point:' line missing")
    return TestLog(test_point, events, settings)


def parse_frame_index(text: str) -> dict[str, datetime]:
    """Frame name (without extension) -> acquisition timestamp, from the HIBMS ``<T>A.txt`` index."""
    lines = text.splitlines()
    header_at = next((i for i, ln in enumerate(lines) if ln.replace(" ", "").startswith("ImgNum,")), None)
    if header_at is None:
        raise ValueError("frame index header 'ImgNum, ...' not found")
    out: dict[str, datetime] = {}
    reader = csv.reader(io.StringIO("\n".join(lines[header_at:])), skipinitialspace=True)
    header = [h.strip() for h in next(reader)]
    i_date, i_time, i_name = header.index("Date"), header.index("MTimeStamp"), header.index("FileName")
    for row in reader:
        if len(row) <= i_name or not row[0].strip().isdigit():
            continue
        stamp = f"{row[i_date].strip()} {row[i_time].strip()}"
        out[row[i_name].strip()] = datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S.%f")
    if not out:
        raise ValueError("frame index has no rows")
    return out


def parse_camera_settings(text: str) -> dict[str, str]:
    """First data row of a camera-settings CSV, keyed by header (units suffix removed)."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise ValueError("camera settings file has no data row")
    keys = [re.sub(r"\(.*\)$", "", k).strip() for k in rows[0]]
    return dict(zip(keys, (v.strip() for v in rows[1]), strict=False))


@dataclass
class HibmsBundle:
    """Paths to one test point's files; frames are decoded lazily from the zip (never extracted)."""

    root: Path
    test_point: str
    _zip: zipfile.ZipFile | None = field(default=None, repr=False)

    def path(self, suffix: str) -> Path:
        return self.root / f"PSI-69_Calibration_{self.test_point}{suffix}"

    @property
    def files(self) -> dict[str, Path]:
        return {
            "test_log": self.path(".txt"),
            "frame_index": self.path("A.txt"),
            "camera_settings": self.path("_HIBMS_Camera_Settings.txt"),
            "frames_zip": self.path("A.zip"),
        }

    def missing(self) -> list[str]:
        return [str(p.name) for p in self.files.values() if not p.is_file()]

    def test_log(self) -> TestLog:
        return parse_test_log(self.files["test_log"].read_text(TEXT_ENCODING))

    def frame_index(self) -> dict[str, datetime]:
        return parse_frame_index(self.files["frame_index"].read_text(TEXT_ENCODING))

    def camera_settings(self) -> dict[str, str]:
        return parse_camera_settings(self.files["camera_settings"].read_text(TEXT_ENCODING))

    def _archive(self) -> zipfile.ZipFile:
        if self._zip is None:
            self._zip = zipfile.ZipFile(self.files["frames_zip"])
        return self._zip

    def frame_names(self) -> list[str]:
        return sorted(n for n in self._archive().namelist() if n.lower().endswith((".tif", ".tiff")))

    def read_frame(self, name: str) -> Any | None:
        """Decoded frame (numpy array, native bit depth) or None if NASA's file is unreadable."""
        import cv2
        import numpy as np

        data = self._archive().read(name)
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None
