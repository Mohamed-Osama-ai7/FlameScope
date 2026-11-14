"""Deterministic uncertainty annotation of Copilot responses (no confidence score, no self-assessment).

Each item names a kind of uncertainty, a stable code, a short explanation and the evidence it rests on
(measurement, chunk or source ids taken from the response itself). Kinds:

* measurement - a stated value: no per-value uncertainty in the source; QUALIFIED or INVALID value.
* data        - the record: missing value; one identifier with several differing records; source not
                VERIFIED (PSI-69 is PENDING_VERIFICATION); ineligible source or absent fuel; not checked
                against the Data Platform database; pooling refused.
* model       - how a number was produced: K is the FLEX team's linear fit of D^2(t) (reported, not
                recomputed); a backend calculation; regimes that cannot share an axis.
* retrieval   - finding evidence: partial evidence, off-topic sentences withheld, no or too little
                evidence, out-of-corpus terms, unknown experiment.

Why no confidence score: there is no calibrated probability and a few dozen labels cannot validate one;
a model's self-reported confidence is never used. Abstention is the only confidence decision; it is
evaluated as selective prediction (coverage and accuracy) in app/rag/uncertainty_eval.py.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# PSI-69 tabulates values without uncertainties (Data Platform: uncertainty columns empty; App. A.1).
NO_REPORTED_UNCERTAINTY = (
    "the PSI-69 table reports this value without an uncertainty; none is assumed or added"
)
K_FIT = (
    "K is the FLEX team's average burning-rate constant from a linear fit of D^2 versus t "
    "(NASA/TP-2015-216046 App. A.1, cited for column semantics); it is reported, not recomputed, "
    "and no fit uncertainty is given"
)


class UncertaintyItem(BaseModel):
    kind: str  # measurement | data | model | retrieval
    code: str
    detail: str
    evidence: list[str] = Field(default_factory=list)  # measurement / chunk / source ids from this response

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.code}"


# abstention reason (prefix) -> (kind, code)
_ABSTENTION = [
    ("the source named in the question is not available", "data", "ineligible_source"),
    ("no table row for fuel", "data", "absent_fuel"),
    ("the question asks for a measured value without naming", "data", "pooling_refused"),
    ("the question asks for a predicted or hypothetical value", "model", "extrapolation_refused"),
    ("the experiment named in the question", "retrieval", "unknown_experiment"),
    ("the question uses terms absent from the evidence corpus", "retrieval", "out_of_corpus_terms"),
    ("retrieved evidence covers only", "retrieval", "insufficient_coverage"),
    ("no usable evidence matched", "retrieval", "no_evidence"),
    ("no retrieved sentence addresses the question", "retrieval", "no_relevant_sentence"),
    ("no claim survived citation validation", "model", "claims_failed_validation"),
    ("language-model provider unavailable", "model", "provider_unavailable"),
    ("cross-regime comparison", "model", "incompatible_regimes"),
]


def annotate(resp: Any) -> list[UncertaintyItem]:
    """Uncertainty items for a CopilotResponse, built only from its own fields."""
    items: dict[str, UncertaintyItem] = {}

    def add(kind: str, code: str, detail: str, evidence: list[str]) -> None:
        key = f"{kind}:{code}"
        if key in items:
            items[key].evidence = sorted(set(items[key].evidence) | set(evidence))
        else:
            items[key] = UncertaintyItem(kind=kind, code=code, detail=detail, evidence=sorted(set(evidence)))

    if resp.abstention_reason:
        for prefix, kind, code in _ABSTENTION:
            if resp.abstention_reason.startswith(prefix):
                ids = [s for s in resp.source_eligibility] if code == "ineligible_source" else []
                add(kind, code, resp.abstention_reason, ids)
                break

    for cl in resp.claims:
        for c in cl.citations:
            if c.eligibility != "VERIFIED_ELIGIBLE":
                add(
                    "data",
                    f"source_{c.eligibility.lower()}",
                    f"{c.source_id} is {c.eligibility}: cited as evidence, not presented as verified",
                    [c.source_id],
                )
            for m in c.measurements:
                if m.evidence_status in ("CLEAN", "QUALIFIED"):
                    add("measurement", "no_reported_uncertainty", NO_REPORTED_UNCERTAINTY, [m.measurement_id])
                if m.evidence_status == "QUALIFIED":
                    add(
                        "measurement",
                        "qualified_value",
                        "value carries a quality flag: " + ", ".join(m.quality_flags),
                        [m.measurement_id],
                    )
                elif m.evidence_status == "INVALID":
                    add(
                        "measurement",
                        "invalid_value",
                        "value flagged invalid: " + ", ".join(m.quality_flags),
                        [m.measurement_id],
                    )
                elif m.evidence_status == "MISSING":
                    add("data", "missing_value", "the source has no value for this cell", [m.measurement_id])
                if m.variable.startswith("burning_rate_constant") and m.evidence_status != "MISSING":
                    add("model", "reported_fit_value", K_FIT, [m.measurement_id])

    if resp.status.value == "answered_with_ambiguity":
        ids = sorted({c.chunk_id for cl in resp.claims for c in cl.citations})
        add(
            "data",
            "duplicate_identifier_records",
            "one source identifier maps to several records with different values; "
            "they are reported separately",
            ids,
        )
    if resp.measurement_verification == "loader_fallback" and any(cl.measurement_ids for cl in resp.claims):
        add(
            "data",
            "not_verified_against_database",
            "measurement ids follow the Data Platform contract but were not checked against its database",
            [m for cl in resp.claims for m in cl.measurement_ids],
        )
    if any(t.tool == "fit_burning_rate_constant" and t.ok for t in resp.tool_results):
        add(
            "model",
            "derived_calculation",
            "a backend calculation (d^2-law fit of user-supplied data) was used",
            [t.tool_result_id for t in resp.tool_results if t.tool == "fit_burning_rate_constant"],
        )
    if resp.claims and resp.evidence.missing:
        add(
            "retrieval",
            "partial_evidence",
            "part of the question is not covered: " + "; ".join(resp.evidence.missing),
            [],
        )
    if any("withheld" in w for w in resp.warnings):
        add("retrieval", "sentences_withheld", next(w for w in resp.warnings if "withheld" in w), [])
    return list(items.values())
