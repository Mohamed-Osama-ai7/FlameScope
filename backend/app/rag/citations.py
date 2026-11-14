"""Validation of LLM output against the retrieved evidence. Nothing unverified reaches the user.

Checks per claim: cited chunk exists in the retrieved set; each quote is a verbatim substring of that
chunk; every number in the claim appears in a cited chunk, the question or a tool result; a number that
belongs to a measurement flagged INVALID or QUALIFIED may appear only together with its marker
("FLAGGED INVALID" / "QUALIFIED"); cited chunks must be usable evidence; evidence type (direct /
analogous) is RECOMPUTED from chunk metadata rather than trusted from the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.rag.measurements import MARKERS, EvidenceStatus
from app.rag.query_analysis import QueryAnalysis
from app.rag.schemas import Chunk, MeasurementRef
from app.rag.tools import ToolResult

_NUM = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?")


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _ws(s: str) -> str:
    return " ".join(s.split())


def numbers(s: str) -> set[str]:
    out: set[str] = set()
    for m in _NUM.findall(s):
        out.add(m)
        out.add(m.lstrip("0") or "0")
        if "." in m:
            out.add(m.rstrip("0").rstrip("."))
    return out


class CitedMeasurement(BaseModel):
    measurement_id: str
    run_id: str
    variable: str
    unit: str
    evidence_status: str
    value: float | None = None  # null unless the value may be stated (CLEAN / QUALIFIED)
    quality_flags: list[str] = Field(default_factory=list)
    source_column: str
    source_locator: str
    provenance: str  # Data Platform route: /api/v1/measurements/{id}/provenance


class Citation(BaseModel):
    chunk_id: str  # UUID = document_chunks.chunk_id
    chunk_key: str
    quote: str
    source_id: str
    source_title: str
    source_url: str = ""
    doi: str = ""
    license: str = ""
    locator: dict[str, str | int | None] = Field(default_factory=dict)
    locator_text: str
    artifact_id: str
    artifact_path: str = ""
    source_artifact_sha256: str
    content_hash: str
    verification_status: str  # registry status of the source
    eligibility: str  # e.g. PENDING_VERIFICATION: never presented as VERIFIED unless it is
    quality_flags: list[str] = Field(default_factory=list)
    measurements: list[CitedMeasurement] = Field(default_factory=list)  # measurements inside the quote
    ingestion_version: str
    chunker_version: str


class ValidatedClaim(BaseModel):
    text: str
    evidence_type: str  # direct | analogous (system-computed)
    citations: list[Citation] = Field(default_factory=list)
    tool_result_ids: list[str] = Field(default_factory=list)
    measurement_ids: list[str] = Field(default_factory=list)
    measurement_status: str | None = None  # worst evidence status among the measurements in this claim


class DroppedClaim(BaseModel):
    text: str
    reasons: list[str]


def _num_unit(value_text: str, unit: str) -> re.Pattern[str]:
    u = re.escape("mole fraction" if unit == "mole_fraction" else unit)
    return re.compile(rf"(?<![\d.]){re.escape(value_text.strip())}'?\s*{u}")


def flagged_number_problems(text: str, chunks: list[Chunk], others: list[Chunk] | None = None) -> list[str]:
    """A flagged value may be repeated only with its marker; a clean twin (same number+unit) is fine.

    `chunks` are the cited chunks; `others` (the rest of the retrieved evidence) count only for the runs
    whose experiment id the claim names, so an uncited row cannot be used to slip a number past the check.
    """
    named = [c for c in (others or []) if c not in chunks and any(e in text for e in c.experiment_ids[:1])]
    refs: list[MeasurementRef] = [m for c in list(chunks) + named for m in c.measurements]
    clean = {
        (m.original_value_text.strip(), m.unit)
        for m in refs
        if m.evidence_status == EvidenceStatus.CLEAN.value
    }
    out: list[str] = []
    low = text.lower()
    for m in refs:  # a missing/invalid cell must not receive ANY number for its variable
        status = EvidenceStatus(m.evidence_status)
        if status not in (EvidenceStatus.MISSING, EvidenceStatus.INVALID):
            continue
        label = m.statement.split(":", 1)[0].split(" ", 1)[-1].lower()  # "FLEX-004 <label>: ..."
        unit = "mole fraction" if m.unit == "mole_fraction" else m.unit
        marker = "MISSING" if status is EvidenceStatus.MISSING else MARKERS[status]
        if label in low and re.search(rf"\d\s*'?\s*{re.escape(unit)}", text) and marker not in text:
            out.append(
                f"gives a number for {m.variable} of {m.run_id}, which is {status.value} in the source"
            )
    for m in refs:
        status = EvidenceStatus(m.evidence_status)
        if status not in MARKERS or not m.original_value_text.strip():
            continue
        if (m.original_value_text.strip(), m.unit) in clean:
            continue
        if _num_unit(m.original_value_text, m.unit).search(text) and MARKERS[status] not in text:
            out.append(
                f"states {m.variable} = {m.original_value_text} {m.unit} without '{MARKERS[status]}' "
                f"(measurement {m.measurement_id} is {status.value}: {', '.join(m.quality_flags)})"
            )
    return out


def measurements_in(quote: str, chunk: Chunk) -> list[MeasurementRef]:
    q = _ws(quote)
    return [m for m in chunk.measurements if _ws(m.statement) in q or q in _ws(m.statement)]


def cited_measurement(m: MeasurementRef) -> CitedMeasurement:
    stateable = m.evidence_status in (EvidenceStatus.CLEAN.value, EvidenceStatus.QUALIFIED.value)
    return CitedMeasurement(
        measurement_id=m.measurement_id,
        run_id=m.run_id,
        variable=m.variable,
        unit=m.unit,
        evidence_status=m.evidence_status,
        value=m.value if stateable else None,
        quality_flags=list(m.quality_flags),
        source_column=m.source_column,
        source_locator=m.source_locator,
        provenance=f"/api/v1/measurements/{m.measurement_id}/provenance",
    )


def make_citation(ch: Chunk, quote: str) -> Citation:
    return Citation(
        chunk_id=ch.chunk_id,
        chunk_key=ch.chunk_key,
        quote=quote,
        source_id=ch.source_id,
        source_title=ch.source_title,
        source_url=ch.source_url,
        doi=ch.doi,
        license=ch.license,
        locator=ch.locator,
        locator_text=ch.locator_text,
        artifact_id=ch.artifact_id,
        artifact_path=ch.artifact_path,
        source_artifact_sha256=ch.source_artifact_sha256,
        content_hash=ch.content_hash,
        verification_status=ch.verification_status,
        eligibility=ch.eligibility,
        quality_flags=list(ch.quality_flags),
        measurements=[cited_measurement(m) for m in measurements_in(quote, ch)],
        ingestion_version=ch.ingestion_version,
        chunker_version=ch.chunker_version,
    )


_SEVERITY = [
    s.value
    for s in (EvidenceStatus.CLEAN, EvidenceStatus.QUALIFIED, EvidenceStatus.MISSING, EvidenceStatus.INVALID)
]


def worst_status(statuses: list[str]) -> str | None:
    return max(statuses, key=_SEVERITY.index) if statuses else None


def classify(chunk: Chunk, qa: QueryAnalysis) -> str:
    """direct = chunk matches every entity the question names (regime, fuel, experiment); else analogous."""
    if qa.regimes and chunk.regime not in qa.regimes:
        return "analogous"
    if qa.fuels and not {f.lower() for f in qa.fuels} & _words(chunk.fuel_or_material or ""):
        # a chunk without that fuel (e.g. PSI record narrative) is context, not a fuel-specific observation
        return "analogous"
    if qa.experiment_ids and not (
        {e.lower() for e in qa.experiment_ids} & {e.lower() for e in chunk.experiment_ids}
    ):
        return "analogous"
    return "direct"


def validate_claims(
    raw: dict[str, Any], evidence: dict[str, Chunk], tools: dict[str, ToolResult], qa: QueryAnalysis
) -> tuple[list[ValidatedClaim], list[DroppedClaim]]:
    kept: list[ValidatedClaim] = []
    dropped: list[DroppedClaim] = []
    tool_text = " ".join(json.dumps(t.result, default=str) for t in tools.values() if t.ok and t.result)
    by_key = {ch.chunk_key: ch for ch in evidence.values()}  # a model may cite the readable key
    for c in raw.get("claims") or []:
        text = str(c.get("text") or "").strip()
        reasons: list[str] = []
        cites: list[Citation] = []
        used_chunks: list[Chunk] = []
        for ci in c.get("citations") or []:
            ref = str(ci.get("chunk_id"))
            ch = evidence.get(ref) or by_key.get(ref)
            quote = _ws(str(ci.get("quote") or ""))
            if ch is None:
                reasons.append(f"cited chunk '{ci.get('chunk_id')}' was not retrieved")
            elif not ch.usable_as_evidence:
                reasons.append(f"cited chunk {ch.chunk_key} is not usable evidence ({ch.eligibility})")
            elif not quote:
                reasons.append(f"empty quote for {ch.chunk_id}")
            elif quote not in _ws(ch.text):
                reasons.append(f"quote is not a verbatim span of {ch.chunk_id}")
            else:
                used_chunks.append(ch)
                cites.append(make_citation(ch, quote))
        tids = [t for t in (c.get("tool_result_ids") or []) if t in tools and tools[t].ok]
        for t in c.get("tool_result_ids") or []:
            if t not in tools or not tools[t].ok:
                reasons.append(f"tool result '{t}' does not exist or failed")
        if not text:
            reasons.append("empty claim")
        if not cites and not tids:
            reasons.append("claim has no valid citation or tool result")
        allowed_numbers = numbers(" ".join([ch.text for ch in used_chunks] + [qa.question, tool_text]))
        stray = sorted(n for n in numbers(text) if n not in allowed_numbers)
        if stray and not reasons:
            reasons.append(f"numbers not present in cited evidence or tool results: {stray}")
        if not reasons:
            reasons += flagged_number_problems(text, used_chunks, list(evidence.values()))
        if reasons:
            dropped.append(DroppedClaim(text=text, reasons=reasons))
            continue
        etype = "direct"
        if used_chunks and any(classify(ch, qa) == "analogous" for ch in used_chunks):
            etype = "analogous"
        if not used_chunks and tids:
            etype = "direct"
        mids = list(dict.fromkeys(m.measurement_id for ci in cites for m in ci.measurements))
        known = {m.measurement_id for ch in evidence.values() for m in ch.measurements}
        mids += [
            m for m in (c.get("measurement_ids") or []) if m not in mids and (m in known or m in tool_text)
        ]
        statuses = [m.evidence_status for ci in cites for m in ci.measurements]
        kept.append(
            ValidatedClaim(
                text=text,
                evidence_type=etype,
                citations=cites,
                tool_result_ids=tids,
                measurement_ids=mids,
                measurement_status=worst_status(statuses),
            )
        )
    return kept, dropped
