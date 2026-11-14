"""Evidence-grounded Scientific Copilot: retrieve -> (tools) -> generate -> validate -> answer or abstain."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.domain.comparison import ComparisonRequest, ObservationDescriptor, validate_comparison
from app.domain.regimes import CombustionRegime
from app.rag.bm25 import tokenize
from app.rag.citations import DroppedClaim, ValidatedClaim, classify, validate_claims
from app.rag.llm import SYSTEM_PROMPT, LLMProvider, LLMUnavailableError
from app.rag.measurements import EvidenceStatus
from app.rag.platform import verify
from app.rag.query_analysis import GENERIC, VALUE_REQUEST, QueryAnalysis, analyse
from app.rag.retriever import HybridRetriever
from app.rag.schemas import Chunk, MeasurementRef, RetrievalMode, SearchFilter, SearchRequest
from app.rag.tools import ToolResult, run_tool, tool_catalog
from app.science.droplet import DropletSeries

# Sufficiency gate (tuned on the dev split only; see docs/14 and eval/rag_questions_v1.jsonl).
COVERAGE_MIN = 0.6
# A generated (non-backend) claim must itself cover this share of the question's content terms; otherwise
# it is an off-topic sentence from a relevant chunk (e.g. a droplet diameter offered for "why was the LLUV
# camera unreliable") and is withheld. Set a priori to 0.5 (not tuned); docs/14 section 6 reports
# the questions on which this behaviour was diagnosed, so those results are not a held-out estimate.
CLAIM_COVERAGE_MIN = 0.5
MAX_LLM_TOOL_CALLS = 3
# questions about a specific test or run (as opposed to publications or the record narrative)
_RUN_QUESTION = re.compile(r"\b(?:tests?|runs?)\b", re.I)


class Status(str, Enum):
    ANSWERED = "answered"
    ANSWERED_WITH_AMBIGUITY = "answered_with_ambiguity"
    COMPARISON_BLOCKED = "comparison_blocked"
    ABSTAINED = "abstained"


class ToolInputs(BaseModel):
    comparison: ComparisonRequest | None = None
    droplet_series: DropletSeries | None = None


class CopilotRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode = "bm25"
    rerank: bool = False
    filters: SearchFilter | None = None
    tool_inputs: ToolInputs | None = None


class EvidenceSummary(BaseModel):
    direct: list[str] = Field(default_factory=list)  # chunk_ids supporting validated direct claims
    analogous: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)  # what was asked for but not found
    flagged: list[str] = Field(default_factory=list)  # requested values that are invalid or qualified


class CopilotResponse(BaseModel):
    status: Status
    answer: str
    claims: list[ValidatedClaim] = Field(default_factory=list)
    evidence: EvidenceSummary = Field(default_factory=EvidenceSummary)
    abstention_reason: str | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    dropped_claims: list[DroppedClaim] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str
    retrieval: dict[str, Any] = Field(default_factory=dict)
    source_eligibility: dict[str, str] = Field(
        default_factory=dict
    )  # source_id -> eligibility of cited sources
    measurement_verification: str = "none"  # platform | loader_fallback | unavailable | none
    notice: str = (
        "Independent research prototype. Answers are limited to retrieved NASA-sourced evidence and "
        "validated "
        "backend tools; not a NASA product or an operational fire-safety system."
    )


_REGIME_PRIMARY = {
    CombustionRegime.FLEX_DROPLET.value: ("burning_rate_constant_mm2_s", "mm^2/s"),
    CombustionRegime.BASS_II_SOLID.value: ("flame_spread_rate", "mm/s"),
    CombustionRegime.SAFFIRE_SPACECRAFT_SCALE.value: ("flame_spread_rate", "mm/s"),
}


def _regime_descriptor(regime: str) -> ObservationDescriptor:
    var, unit = _REGIME_PRIMARY[regime]
    return ObservationDescriptor(
        investigation_id=regime, regime=CombustionRegime(regime), variable=var, unit=unit
    )


class ScientificCopilot:
    def __init__(self, retriever: HybridRetriever, provider: LLMProvider) -> None:
        self.retriever = retriever
        self.provider = provider
        self.vocab = set(retriever.bm25.idf)
        self.sources: dict[str, tuple[str, str, bool]] = {}  # source_id -> (eligibility, reason, usable)
        for c in retriever.chunks:
            self.sources.setdefault(c.source_id, (c.eligibility, c.exclusion_reason, c.usable_as_evidence))
        self.corpus_fuels = {
            w
            for c in retriever.chunks
            if c.usable_as_evidence
            for w in re.findall(r"[a-z0-9]+", (c.fuel_or_material or "").lower())
        }

    # ------------------------------------------------------------------ gates

    def _unsupported_terms(self, qa: QueryAnalysis) -> list[str]:

        def known(t: str) -> bool:
            variants = {t} | {v for v in (t[:-1], t[:-2], t[:-3], t[:-3] + "e", t[:-2] + "e") if len(v) >= 3}
            return bool(variants & self.vocab) or bool(variants & GENERIC)

        # compound tokens (cabin-air) are skipped: their parts are checked on their own
        return sorted(
            {
                t
                for t in qa.content_tokens
                if len(t) >= 4 and not any(ch in t for ch in "-_./") and not known(t)
            }
        )

    @staticmethod
    def _measurement_resolved(qa: QueryAnalysis, hits: list[Chunk]) -> bool:
        """Every named experiment has a retrieved table row stating every requested variable."""
        if not (qa.experiment_ids and qa.variables):
            return False
        for e in qa.experiment_ids:
            rows = [
                c
                for c in hits
                if c.doc_type.value == "table_row" and e.lower() in {x.lower() for x in c.experiment_ids}
            ]
            have = {m.variable for c in rows for m in c.measurements}
            if not rows or not set(qa.variables) <= have:
                return False
        return True

    def _sufficiency(self, qa: QueryAnalysis, hits: list[Chunk]) -> tuple[str | None, list[str]]:
        missing: list[str] = []
        if not hits and qa.experiment_ids:
            return "the experiment named in the question has no usable evidence", [
                f"evidence for experiment '{e}'" for e in qa.experiment_ids
            ]
        if not hits:
            return "no usable evidence matched the question and filters", ["any matching evidence"]
        have_ids = {e.lower() for c in hits for e in c.experiment_ids}
        for e in qa.experiment_ids:
            if e.lower() not in have_ids:
                missing.append(f"evidence for experiment '{e}'")
        if missing:
            return "the experiment named in the question was not found in the usable evidence", missing
        # A reported value, or a question about which test/run used a fuel, needs a table row for that fuel.
        # Without the run clause, "Which FLEX test used a propanol droplet?" was answered with propanol
        # publication titles that a reader could take for FLEX runs (v4 holdout A34, judged misleading).
        if qa.numeric_lookup or _RUN_QUESTION.search(qa.question):
            gone = [f for f in qa.fuels if f.lower() not in self.corpus_fuels]
            if gone and len(gone) == len(qa.fuels):
                return f"no table row for fuel(s) {', '.join(gone)} in the usable evidence", [
                    f"FLEX runs or reported values for {f}" for f in gone
                ]
            missing += [f"reported values for {f}" for f in gone]  # partial coverage: answer, but disclose
        oov = self._unsupported_terms(qa)
        if oov:
            return f"the question uses terms absent from the evidence corpus: {', '.join(oov)}", [
                f"evidence mentioning '{t}'" for t in oov
            ]
        if (
            qa.variables
            and qa.numeric_lookup
            and not qa.experiment_ids
            and not qa.statistical
            and VALUE_REQUEST.search(qa.question)
        ):
            # per-run values are never pooled or picked at random to answer a general value question
            return (
                "the question asks for a measured value without naming a FLEX test; values are reported per "
                "run only (name a test, or ask for a descriptive summary such as a median or range)",
                [f"a specific test for {', '.join(qa.variables)}"],
            )
        if self._measurement_resolved(qa, hits):
            # the backend states the exact measurement; loose wording cannot change it (v4 diagnostic A03).
            # The out-of-vocabulary gate above still applies.
            return None, missing
        pool: set[str] = set()
        for c in hits:
            pool |= set(tokenize(c.text + " " + " ".join(c.experiment_ids)))
        toks = set(qa.content_tokens)
        cov = len(toks & pool) / len(toks) if toks else 0.0
        if cov < COVERAGE_MIN:
            gone = sorted(toks - pool)
            return f"retrieved evidence covers only {cov:.0%} of the question's terms", [
                f"evidence mentioning '{t}'" for t in gone[:5]
            ]
        return None, missing

    # ------------------------------------------------------------------ orchestration

    def _filters(self, req: CopilotRequest, qa: QueryAnalysis) -> SearchFilter:
        f = (req.filters or SearchFilter()).model_copy()  # ineligible chunks are excluded by the retriever
        if f.regimes is None and len(qa.regimes) == 1:
            f.regimes = list(qa.regimes)
        if f.experiment_ids is None and qa.experiment_ids:
            f.experiment_ids = list(
                qa.experiment_ids
            )  # metadata filter: only chunks of the named experiment(s)
        return f

    def _auto_tools(self, req: CopilotRequest, qa: QueryAnalysis, tools: dict[str, ToolResult]) -> None:
        def add(name: str, args: dict[str, Any]) -> None:
            tid = f"T{len(tools) + 1}"
            tools[tid] = run_tool(tid, name, args)

        if qa.numeric_lookup:
            for e in qa.experiment_ids:
                wanted: list[str | None] = list(qa.variables) or [None]
                for v in wanted:
                    add("get_flex_run", {"experiment_id": e, "variable": v})
        if qa.statistical and len(qa.fuels) == 1 and (not qa.regimes or "flex_droplet" in qa.regimes):
            add("flex_summary", {"fuel": qa.fuels[0]})
        if req.tool_inputs and req.tool_inputs.comparison:
            add("validate_comparison", req.tool_inputs.comparison.model_dump(mode="json"))
        if req.tool_inputs and req.tool_inputs.droplet_series:
            add("fit_burning_rate_constant", req.tool_inputs.droplet_series.model_dump(mode="json"))

    def _source_gate(self, qa: QueryAnalysis) -> tuple[str | None, list[str], list[str]]:
        """A question about a named source that is not usable abstains with the source's status."""
        if not qa.sources:
            return None, [], []
        bad = [s for s in qa.sources if not self.sources.get(s, ("UNREGISTERED", "", False))[2]]
        notes = []
        for s in bad:
            elig, why, _ = self.sources.get(s, ("UNREGISTERED", "not in the evidence corpus", False))
            notes.append(f"{s} is {elig}: {why}")
        if bad and len(bad) == len(qa.sources):
            return (
                "the source named in the question is not available as evidence; " + " | ".join(notes),
                [f"usable evidence from {s}" for s in bad],
                notes,
            )
        return None, [f"usable evidence from {s}" for s in bad], notes

    @staticmethod
    def _measurement_claims(qa: QueryAnalysis, chunks: list[Chunk]) -> list[dict[str, Any]]:
        """Backend-generated claims for 'variable X of experiment Y': the verbatim statement of the
        measurement (value, or MISSING / FLAGGED INVALID / QUALIFIED). No number is produced by a model."""
        if not (qa.experiment_ids and qa.variables):
            return []
        want = {e.lower() for e in qa.experiment_ids}
        out: list[dict[str, Any]] = []
        for c in chunks:
            if c.doc_type.value != "table_row" or not want & {e.lower() for e in c.experiment_ids}:
                continue
            for m in c.measurements:
                if m.variable in qa.variables:
                    out.append(
                        {
                            "text": m.statement,
                            "evidence_type": "direct",
                            "citations": [{"chunk_id": c.chunk_id, "quote": m.statement}],
                            "tool_result_ids": [],
                            "measurement_ids": [m.measurement_id],
                            "origin": "backend_measurement",
                        }
                    )
        return out

    @staticmethod
    def _on_topic(
        qa: QueryAnalysis, claims: list[ValidatedClaim], backend_texts: set[str]
    ) -> tuple[list[ValidatedClaim], int]:
        ids = {t for e in qa.experiment_ids for t in tokenize(e)}
        focus = {t for t in qa.content_tokens if t not in ids and t not in {"flex", "psi", "test", "run"}}
        if not focus:
            return claims, 0
        keep: list[ValidatedClaim] = []
        for cl in claims:
            if cl.text in backend_texts or not cl.citations:
                keep.append(cl)  # backend measurement statements and tool claims are exact by design
                continue
            words = set(tokenize(cl.text))
            if len(focus & words) / len(focus) >= CLAIM_COVERAGE_MIN:
                keep.append(cl)
        return keep, len(claims) - len(keep)

    def ask(self, req: CopilotRequest) -> CopilotResponse:
        qa = analyse(req.question)
        flt = self._filters(req, qa)
        res = self.retriever.search(
            SearchRequest(query=req.question, top_k=req.top_k, mode=req.mode, rerank=req.rerank, filters=flt)
        )
        chunks = [h.chunk for h in res.hits]
        evidence = {c.chunk_id: c for c in chunks}
        meta = {
            "mode": res.mode,
            "dense_backend": res.dense_backend,
            "reranked": res.reranked,
            "scores": {h.chunk.chunk_id: round(h.score, 6) for h in res.hits},
        }
        base: dict[str, Any] = {
            "provider": self.provider.name,
            "retrieved_chunk_ids": list(evidence),
            "warnings": list(res.warnings),
            "retrieval": meta,
        }
        tools: dict[str, ToolResult] = {}

        if qa.cross_regime_comparison:  # deterministic comparison gate (docs/03_scientific_gates.md)
            reasons: list[str] = []
            allowed = False
            regs = qa.regimes
            for i in range(len(regs)):
                for j in range(i + 1, len(regs)):
                    r = validate_comparison(_regime_descriptor(regs[i]), _regime_descriptor(regs[j]))
                    tools[f"G{i}{j}"] = ToolResult(
                        tool_result_id=f"G{i}{j}",
                        tool="validate_comparison",
                        ok=True,
                        arguments={"a": regs[i], "b": regs[j]},
                        result=r.model_dump(mode="json"),
                    )
                    allowed = allowed or r.shared_axis_allowed
                    reasons += r.reasons
            if not allowed:
                ctx = [c.chunk_id for c in chunks if classify(c, qa) == "analogous"]
                return CopilotResponse(
                    status=Status.COMPARISON_BLOCKED,
                    tool_results=list(tools.values()),
                    answer=(
                        "These combustion regimes cannot be compared directly: "
                        + "; ".join(sorted(set(reasons)))
                        + ". Evidence for each regime can only be read separately, as analogous context."
                    ),
                    abstention_reason="cross-regime comparison without validated eligibility",
                    evidence=EvidenceSummary(analogous=ctx),
                    **base,
                )

        src_reason, src_missing, src_notes = self._source_gate(qa)
        if src_reason:
            return CopilotResponse(
                status=Status.ABSTAINED,
                answer="",
                abstention_reason=src_reason,
                evidence=EvidenceSummary(missing=src_missing),
                source_eligibility={
                    s: self.sources.get(s, ("UNREGISTERED", "", False))[0] for s in qa.sources
                },
                **base,
            )
        base["warnings"] += src_notes

        reason, missing = self._sufficiency(qa, chunks)
        missing += src_missing
        if reason:
            return CopilotResponse(
                status=Status.ABSTAINED,
                answer="",
                abstention_reason=reason,
                evidence=EvidenceSummary(missing=missing),
                **base,
            )

        self._auto_tools(req, qa, tools)
        payload: dict[str, Any] = {
            "question": req.question,
            "evidence": [
                {
                    "chunk_id": c.chunk_id,
                    "source_title": c.source_title,
                    "locator": c.locator_text,
                    "regime": c.regime,
                    "fuel_or_material": c.fuel_or_material,
                    "text": c.text,
                }
                for c in chunks
            ],
            "tool_results": [t.model_dump(mode="json") for t in tools.values()],
            "tools": tool_catalog(),
        }
        try:
            out = self.provider.complete(SYSTEM_PROMPT, payload)
            calls = [c for c in (out.get("tool_calls") or []) if isinstance(c, dict)][:MAX_LLM_TOOL_CALLS]
            if calls and not out.get("claims"):
                for c in calls:
                    tid = f"T{len(tools) + 1}"
                    tools[tid] = run_tool(tid, str(c.get("name")), c.get("arguments") or {})
                payload["tool_results"] = [t.model_dump(mode="json") for t in tools.values()]
                payload.pop("tools")
                out = self.provider.complete(SYSTEM_PROMPT, payload)
        except LLMUnavailableError as exc:
            return CopilotResponse(
                status=Status.ABSTAINED,
                answer="",
                tool_results=list(tools.values()),
                abstention_reason=f"language-model provider unavailable: {exc}",
                **base,
            )

        mclaims = self._measurement_claims(qa, chunks)
        if mclaims:  # the backend statement replaces the generic "tool returned a result" placeholder
            texts = {m["text"] for m in mclaims}
            rest = [
                c
                for c in (out.get("claims") or [])
                if c.get("text") not in texts
                and not (
                    not c.get("citations")
                    and any(
                        tools.get(t) and tools[t].tool == "get_flex_run"
                        for t in c.get("tool_result_ids") or []
                    )
                )
            ]
            out = {**out, "claims": mclaims + rest, "abstain": False}

        claims, dropped = validate_claims(out, evidence, tools, qa)
        claims, off_topic = self._on_topic(qa, claims, {m["text"] for m in mclaims})
        if off_topic:
            base["warnings"].append(
                f"{off_topic} retrieved sentence(s) withheld: they do not address the question's terms"
            )

        # contract B.5: cited measurements are checked against the Data Platform when it is connected
        refs: dict[str, MeasurementRef] = {m.measurement_id: m for c in chunks for m in c.measurements}
        cited = [refs[i] for cl in claims for i in cl.measurement_ids if i in refs]
        ver = verify(list({m.measurement_id: m for m in cited}.values()))
        base["measurement_verification"] = ver.mode
        if cited and ver.mode == "loader_fallback":
            base["warnings"].append(ver.detail)
        if ver.problems:
            keep = []
            for cl in claims:
                bad = {i: ver.problems[i] for i in cl.measurement_ids if i in ver.problems}
                if bad:
                    dropped.append(
                        DroppedClaim(text=cl.text, reasons=[f"{i}: {'; '.join(p)}" for i, p in bad.items()])
                    )
                else:
                    keep.append(cl)
            claims = keep
            base["warnings"].append(f"measurement verification ({ver.mode}): {ver.detail}")

        if out.get("abstain") or not claims:
            why = out.get("abstain_reason") or (
                "no claim survived citation validation"
                if dropped
                else "no retrieved sentence addresses the question"
                if off_topic
                else "the model found no supported answer"
            )
            return CopilotResponse(
                status=Status.ABSTAINED,
                answer="",
                abstention_reason=str(why),
                tool_results=list(tools.values()),
                dropped_claims=dropped,
                evidence=EvidenceSummary(missing=missing),
                **base,
            )

        summ = EvidenceSummary(missing=missing)
        for cl in claims:
            for mid in cl.measurement_ids:
                m = refs.get(mid)
                if m is None or m.variable not in qa.variables:
                    continue
                if m.evidence_status == EvidenceStatus.MISSING.value:
                    summ.missing.append(f"{m.run_id} {m.variable}: no value in the source")
                elif m.evidence_status in (EvidenceStatus.INVALID.value, EvidenceStatus.QUALIFIED.value):
                    summ.flagged.append(
                        f"{m.run_id} {m.variable}: {m.evidence_status} ({', '.join(m.quality_flags)})"
                    )
            ids = [c.chunk_id for c in cl.citations]
            tgt = summ.direct if cl.evidence_type == "direct" else summ.analogous
            tgt += [i for i in ids if i not in tgt]
        status = Status.ANSWERED
        dup = [
            i
            for i in qa.experiment_ids
            if len(
                {
                    c.chunk_id
                    for c in chunks
                    if c.doc_type.value == "table_row" and i.lower() in {e.lower() for e in c.experiment_ids}
                }
            )
            > 1
        ]
        if dup:
            status = Status.ANSWERED_WITH_AMBIGUITY
            base["warnings"].append(
                f"identifier(s) {', '.join(dup)} map to more than one distinct source record; values are "
                "reported per record and must not be merged"
            )
        for t in tools.values():
            if t.ok and t.result and t.result.get("ambiguous_identifier"):
                status = Status.ANSWERED_WITH_AMBIGUITY
        if dropped:
            base["warnings"].append(f"{len(dropped)} generated claim(s) failed validation and were removed")
        if summ.flagged or any("no value in the source" in x for x in summ.missing):
            base["warnings"].append(
                "a requested value is missing or flagged in the source; it is reported as such and is not "
                "usable as a clean measurement"
            )
        base["source_eligibility"] = {ci.source_id: ci.eligibility for cl in claims for ci in cl.citations}
        return CopilotResponse(
            status=status,
            answer=" ".join(c.text for c in claims),
            claims=claims,
            tool_results=list(tools.values()),
            dropped_claims=dropped,
            evidence=summ,
            **base,
        )
