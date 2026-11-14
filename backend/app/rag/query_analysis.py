"""Deterministic question analysis: entities, regimes, comparison intent. No LLM involved."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.regimes import CombustionRegime
from app.rag.bm25 import tokenize

FUELS = ("methanol", "heptane")  # the two liquid fuels present in the acquired FLEX table
# Fuel/material names the question may mention; only those in the evidence can be answered about.
KNOWN_FUELS = (
    "methanol",
    "ethanol",
    "propanol",
    "methane",
    "ethane",
    "propane",
    "butane",
    "pentane",
    "hexane",
    "heptane",
    "octane",
    "decane",
    "dodecane",
    "kerosene",
    "hydrogen",
    "acetylene",
    "pmma",
    "cellulose",
)
REGIME_CUES: dict[str, tuple[str, ...]] = {
    CombustionRegime.FLEX_DROPLET.value: (
        "flex",
        "psi-69",
        "droplet",
        "methanol",
        "heptane",
        "mdca",
        "d2",
        "d^2",
    ),
    CombustionRegime.BASS_II_SOLID.value: ("bass", "psi-25", "pmma", "sibal", "solid fuel", "glovebox"),
    CombustionRegime.SAFFIRE_SPACECRAFT_SCALE.value: ("saffire", "psi-98", "cygnus"),
}
_COMPARE = re.compile(
    r"\b(compare|compared|comparison|versus|vs\.?|than|higher|lower|faster|slower|"
    r"same as|difference|differ)\b",
    re.I,
)
_EXP_ID = re.compile(r"\b(flex-\d{1,3}|\d{2,3}[a-z]{1,3}\d{2,3})\b", re.I)
_FLEX_NUM = re.compile(r"\bflex(?:\s+(?:test|run|experiment))?\s*#?\s*(\d{1,3})\b", re.I)
_NUMERIC_INTENT = re.compile(
    r"\b(burning[- ]rate|constant|k value|diameter|pressure|mole fraction|burn time|how long|"
    r"reported value)\b",
    re.I,
)
# Phrases naming a measured variable -> Data Platform variable (most specific first).
VARIABLE_CUES: tuple[tuple[str, str], ...] = (
    (
        # D0 is measured at igniter-on (PSI-69 / NASA/TP App. A.1); paraphrases from benchmark v3 dev G01, G11
        r"initial (droplet )?diameter|\bd0\b|droplet initial diameter|droplet at ignition"
        r"|start(?:ed|ing)? (?:with )?(?:the )?(?:larger |smaller )?droplet"
        r"|how (?:large|big) was the droplet",
        "initial_droplet_diameter",
    ),
    (r"extinction (droplet )?diameter|flame extinction diameter|\bdext\b", "extinction_diameter"),
    (r"burning[- ]rate constant|burning[- ]rate|\bk value\b|\breported k\b", "burning_rate_constant_mm2_s"),
    (r"burn time|how long did .* burn", "burn_time"),
    (r"ambient pressure|\bpressure\b", "ambient_pressure"),
    (r"\boxygen\b|\bo2\b", "ambient_oxygen_mole_fraction"),
    (r"\bnitrogen\b|\bn2\b", "ambient_nitrogen_mole_fraction"),
    (r"carbon dioxide|\bco2\b", "co2_mole_fraction"),
    (r"\bhelium\b|\bhe\b", "ambient_helium_mole_fraction"),
)
# Questions that name a specific source; eligibility decides whether it may be answered at all.
SOURCE_CUES: dict[str, tuple[str, ...]] = {
    "PSI-25": (r"bass[- ]?ii", r"\bbass\b", r"psi[- ]?25\b", r"burning and suppression of solids"),
    "PSI-98": (r"saffire", r"psi[- ]?98\b", r"spacecraft fire safety experiment"),
    "NASA-TP-2015-216046": (
        r"nasa/tp",
        r"tp-2015",
        r"216046",
        r"technical (publication|report)",
        r"\bntrs\b",
    ),
    "PSI-69": (r"\bflex\b", r"psi[- ]?69\b", r"flame extinguishment"),
}
# A request for a value (as opposed to "which publication studied diameter effects").
VALUE_REQUEST = re.compile(
    r"\bwhat (?:was|is|were|are) the\b|\bhow (?:large|long|much|high|fast)\b|\bvalue\b"
    r"|\bwhat \w+ was reported\b",
    re.I,
)
_STAT_INTENT = re.compile(
    r"\b(how many|median|mean|average|range|minimum|maximum|distribution|count)\b", re.I
)
# Words that carry no scientific content in a question; they must not trigger "unsupported term" abstention.
GENERIC = frozenset(
    "measure measured report reported state stated describe described explain tell value values find give "
    "show list used use using study studied experiment experiments investigation investigations question "
    "answer information data record records entry entries listed number numbers detail details particular "
    "specific mention mentioned according source sources nasa say says note noted observe observed "
    "cover covers covered house housed address addressed share shared form formed seen see saw occur "
    "occurred happen happened begin began regard regarding respect conduct perform performed carry "
    "include included involve involved contain contained lead make made take took get got come came "
    "become did does done kind type way behave behaves behaved behavior behaviour "
    "could would should might may can will must shall".split()
)


@dataclass
class QueryAnalysis:
    question: str
    fuels: list[str] = field(default_factory=list)
    regimes: list[str] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    comparison: bool = False
    numeric_lookup: bool = False
    statistical: bool = False
    content_tokens: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)  # platform variable names asked about
    sources: list[str] = field(default_factory=list)  # source ids named in the question

    @property
    def cross_regime_comparison(self) -> bool:
        return self.comparison and len(self.regimes) >= 2


def analyse(question: str) -> QueryAnalysis:
    q = question.lower()
    regimes = [
        r
        for r, cues in REGIME_CUES.items()
        if any(re.search(rf"(?<![a-z0-9]){re.escape(c)}", q) for c in cues)
    ]
    # a fuel word alone implies FLEX only; do not count it as a second regime next to others
    fuels = [f for f in KNOWN_FUELS if re.search(rf"(?<![a-z]){f}", q)]
    ids = []
    for m in _EXP_ID.findall(question):
        ids.append(m.upper())
    for n in _FLEX_NUM.findall(question):
        ids.append(f"FLEX-{int(n):03d}")
    # comparison cue words carry intent, not scientific content (benchmark v3 dev G09)
    toks = [
        t
        for t in tokenize(question)
        if t not in GENERIC and not re.fullmatch(r"\d+", t) and not _COMPARE.fullmatch(t)
    ]
    return QueryAnalysis(
        question=question,
        fuels=[f.capitalize() for f in fuels],
        regimes=regimes,
        experiment_ids=sorted(set(ids)),
        comparison=bool(_COMPARE.search(question)),
        numeric_lookup=bool(_NUMERIC_INTENT.search(question)),
        statistical=bool(_STAT_INTENT.search(question)),
        content_tokens=toks,
        variables=_variables(q),
        sources=[s for s, pats in SOURCE_CUES.items() if any(re.search(p, q) for p in pats)],
    )


COMPOSITION_VARS = (
    "ambient_oxygen_mole_fraction",
    "ambient_nitrogen_mole_fraction",
    "co2_mole_fraction",
    "ambient_helium_mole_fraction",
)


def _variables(q: str) -> list[str]:
    out: list[str] = list(COMPOSITION_VARS) if re.search(r"\bcomposition\b|mole fractions", q) else []
    rest = q
    for pat, var in VARIABLE_CUES:
        if re.search(pat, rest):
            if var not in out:
                out.append(var)
            rest = re.sub(pat, " ", rest)  # "initial droplet diameter" must not also count as a bare match
    return out
