"""Canonical mapping of the PSI-69 FLEX experimental-table headers.

Raw files and raw headers are never modified; this mapping is applied when reading. Each entry
cites the NASA source that resolves its meaning. Evidence:

NASA/TP-2015-216046 (also E-18493, GRC-E-DAA-TN5314), Dietrich et al., "Detailed Results From the
Flame Extinguishment Experiment (FLEX) March 2009 to December 2011", NASA Glenn, November 2015.
https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf
Appendix A.1 (printed p. 19) defines the Table IX columns; Table IX (printed p. 20 onward) gives
units and the O2/N2/CO2/He composition headers.
"""
from __future__ import annotations

from pydantic import BaseModel

NASA_TP_FLEX = (
    "NASA/TP-2015-216046, Dietrich et al. (2015), Detailed Results From the Flame Extinguishment "
    "Experiment (FLEX) March 2009 to December 2011"
)
NASA_TP_FLEX_URL = "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf"


class ColumnMapping(BaseModel):
    raw_header: str
    canonical: str
    unit: str | None
    value_origin: str  # "reported_in_source" for every column of this table
    evidence: str


REPORTED = "reported_in_source"

FLEX_COLUMNS: dict[str, ColumnMapping] = {
    m.raw_header: m
    for m in [
        ColumnMapping(
            raw_header="Burning rate; mm",
            canonical="burning_rate_constant_mm2_s",
            unit="mm^2/s",
            value_origin=REPORTED,
            evidence=(
                f"{NASA_TP_FLEX}, Appendix A.1 p.19: 'average burning rate constant from a linear "
                "fit of the droplet diameter squared versus time from shortly after ignition to "
                "extinction'; Table IX header unit mm2/s. PSI header lost the '2/s'."
            ),
        ),
        ColumnMapping(
            raw_header="CO initial ambient composition; mole fraction",
            canonical="co2_mole_fraction",
            unit="mole_fraction",
            value_origin=REPORTED,
            evidence=(
                f"{NASA_TP_FLEX}, Table IX composition headers O2 N2 CO2 He; Appendix A.1 p.19: "
                "'CO2-ambient carbon dioxide mole fraction'. PSI header lost the subscript."
            ),
        ),
        ColumnMapping(
            raw_header="O initial ambient composition; mole fraction",
            canonical="ambient_oxygen_mole_fraction",
            unit="mole_fraction",
            value_origin=REPORTED,
            evidence=f"{NASA_TP_FLEX}, Table IX header O2; Appendix A.1 'O2-ambient oxygen mole fraction'.",
        ),
        ColumnMapping(
            raw_header="N initial ambient composition; mole fraction",
            canonical="ambient_nitrogen_mole_fraction",
            unit="mole_fraction",
            value_origin=REPORTED,
            evidence=f"{NASA_TP_FLEX}, Table IX header N2; Appendix A.1 'N2-ambient nitrogen mole fraction'.",
        ),
        ColumnMapping(
            raw_header="He initial ambient composition; mole fraction",
            canonical="ambient_helium_mole_fraction",
            unit="mole_fraction",
            value_origin=REPORTED,
            evidence=f"{NASA_TP_FLEX}, Table IX header He (not defined in Appendix A.1 list).",
        ),
        ColumnMapping(
            raw_header="Ambient pressure; mmHg",
            canonical="ambient_pressure",
            unit="mmHg",
            value_origin=REPORTED,
            evidence=f"{NASA_TP_FLEX}, Table IX header 'Ambient pressure, mmHg'.",
        ),
        ColumnMapping(
            raw_header="Droplet initial diameter; mm",
            canonical="initial_droplet_diameter",
            unit="mm",
            value_origin=REPORTED,
            evidence=(
                f"{NASA_TP_FLEX}, Appendix A.1 'Actual D0' at igniter-on; droplet size uncertainty "
                "+/-50 um (sec. 3.1.2, p.8)."
            ),
        ),
        ColumnMapping(
            raw_header="Visible flame extinction diameter; mm",
            canonical="extinction_diameter",
            unit="mm",
            value_origin=REPORTED,
            evidence=(
                f"{NASA_TP_FLEX}, Appendix A.1: '-' means no extinction (completion/disruption); "
                "some values extrapolated when the droplet left the HiBMs field of view."
            ),
        ),
    ]
}


def canonical_name(raw_header: str) -> str:
    """Map a raw PSI-69 header to its canonical name; unknown headers raise KeyError."""
    return FLEX_COLUMNS[raw_header].canonical
