from typing import Any

from app.rag.copilot import CopilotRequest, Status, ToolInputs
from app.rag.llm import ExtractiveProvider, LLMUnavailableError
from tests.conftest import ScriptedProvider

ROW70 = "PSI-69:row:070"


def ask(cop, q, **kw):
    return cop.ask(CopilotRequest(question=q, mode="bm25", **kw))


def claim(chunk_id: str, quote: str, text: str | None = None, etype: str = "direct") -> dict[str, Any]:
    return {
        "text": text or quote,
        "evidence_type": etype,
        "citations": [{"chunk_id": chunk_id, "quote": quote}],
        "tool_result_ids": [],
    }


def out(*claims: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "answer": "a",
        "claims": list(claims),
        "abstain": False,
        "abstain_reason": None,
        "tool_calls": [],
        **extra,
    }


HW = "Which hardware housed the FLEX droplet investigation?"


def test_extractive_answer_is_cited_and_traceable(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), HW)
    assert r.status is Status.ANSWERED
    cites = {c.chunk_key: c for cl in r.claims for c in cl.citations}
    c = cites["PSI-69:meta:summary"]
    assert "Multi-user Droplet Combustion" in c.quote
    assert c.content_hash and c.ingestion_version and c.locator_text and c.source_id == "PSI-69"
    assert c.artifact_id and c.source_artifact_sha256 and c.eligibility == "PENDING_VERIFICATION"
    assert c.chunk_id in r.evidence.direct


def test_numbers_come_from_evidence_and_tools(make_copilot):
    r = ask(
        make_copilot(ExtractiveProvider()),
        "What burning-rate constant K was reported for FLEX test 1 (identifier 20CAL08)?",
    )
    assert r.status is Status.ANSWERED
    assert "0.52" in r.answer
    t = next(t for t in r.tool_results if t.tool == "get_flex_run")
    m = t.result["records"][0]["measurements"]
    assert [x["variable"] for x in m] == ["burning_rate_constant_mm2_s"] and m[0]["value"] == 0.52
    assert r.claims[0].measurement_ids == [m[0]["measurement_id"]]
    assert r.claims[0].citations[0].measurements[0].provenance.endswith("/provenance")


def test_hallucinated_citation_is_dropped_and_copilot_abstains(make_copilot):
    p = ScriptedProvider(out(claim("PSI-69:row:999", "K 9.99 mm^2/s")))
    r = ask(make_copilot(p), "What happened in FLEX-070?")
    assert r.status is Status.ABSTAINED and r.dropped_claims
    assert "not retrieved" in r.dropped_claims[0].reasons[0]


def test_non_verbatim_quote_is_rejected(make_copilot):
    p = ScriptedProvider(out(claim(ROW70, "FLEX-070 reported burning-rate constant K: 0.99 mm^2/s")))
    r = ask(make_copilot(p), "What happened in FLEX-070?")
    assert r.status is Status.ABSTAINED
    assert "verbatim" in r.dropped_claims[0].reasons[0]


def test_invented_number_in_claim_text_is_rejected(make_copilot):
    quote = "FLEX-070 reported burning-rate constant K: 0.41 mm^2/s"
    good = claim(ROW70, quote, text="The reported K is 0.41 mm^2/s.")
    bad = claim(ROW70, quote, text="The reported K is 0.41 mm^2/s, i.e. 0.77 after correction.")
    r = ask(make_copilot(ScriptedProvider(out(good, bad))), "What happened in FLEX-070?")
    assert [c.text for c in r.claims] == ["The reported K is 0.41 mm^2/s."]
    assert any("numbers not present" in x for d in r.dropped_claims for x in d.reasons)
    assert any("failed validation" in w for w in r.warnings)


def test_claim_without_support_is_removed(make_copilot):
    uncited = {"text": "FLEX proves X.", "evidence_type": "direct", "citations": [], "tool_result_ids": []}
    r = ask(make_copilot(ScriptedProvider(out(uncited))), HW)
    assert r.status is Status.ABSTAINED and "no valid citation" in r.dropped_claims[0].reasons[0]


def test_evidence_type_is_recomputed_not_trusted(make_copilot):
    # the question asks about FLEX-070 but the model cites FLEX-073 and labels it "direct"
    q = "What was the reported K for FLEX-070 and FLEX-073?"
    c = claim("PSI-69:row:073", "FLEX-073 reported burning-rate constant K: 0.56 mm^2/s")
    r = ask(make_copilot(ScriptedProvider(out(c))), q)
    assert r.claims[0].evidence_type == "direct"  # 073 is named in the question -> genuinely direct
    r2 = ask(make_copilot(ScriptedProvider(out(c))), "What happened in FLEX-070?")
    kept = [cl for cl in r2.claims if "FLEX-073" in cl.text]
    assert r2.status is Status.ABSTAINED or all(cl.evidence_type == "analogous" for cl in kept)


def test_cross_regime_comparison_is_blocked_by_the_gate(make_copilot):
    r = ask(
        make_copilot(ExtractiveProvider()),
        "Compare the burning-rate constant of FLEX heptane with the flame spread rate in BASS-II.",
    )
    assert r.status is Status.COMPARISON_BLOCKED and not r.claims
    assert "cannot be compared directly" in r.answer
    assert any(
        t.tool == "validate_comparison" and not t.result["shared_axis_allowed"] for t in r.tool_results
    )


def test_quarantined_source_is_never_used(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), "What flame spread rate was measured in SAFFIRE-I?")
    assert r.status is Status.ABSTAINED and not r.claims and r.evidence.missing
    assert "QUARANTINED" in r.abstention_reason and not r.retrieved_chunk_ids


def test_unknown_experiment_and_unsupported_terms_abstain(make_copilot):
    cop = make_copilot(ExtractiveProvider())
    r = ask(cop, "What was the reported K for FLEX test 999?")
    assert r.status is Status.ABSTAINED and "999" in " ".join(r.evidence.missing)
    r = ask(cop, "What was the reported burning-rate constant for ethanol droplets in FLEX?")
    assert r.status is Status.ABSTAINED and "ethanol" in r.abstention_reason.lower()
    r = ask(cop, "What will FLEX results predict for burning rates on Mars?")
    assert r.status is Status.ABSTAINED and r.abstention_reason


def test_duplicate_identifier_is_reported_as_ambiguity(make_copilot):
    r = ask(make_copilot(ExtractiveProvider()), "Which records share the source identifier 193F001?")
    assert r.status is Status.ANSWERED_WITH_AMBIGUITY
    assert any("more than one distinct source record" in w for w in r.warnings)
    keys = {c.chunk_key for cl in r.claims for c in cl.citations}
    assert {"PSI-69:row:070", "PSI-69:row:073"} <= keys


def test_provider_failure_abstains_instead_of_guessing(make_copilot):
    class Down:
        name = "down"

        def complete(self, system, payload):
            raise LLMUnavailableError("boom")

    r = ask(make_copilot(Down()), HW)
    assert r.status is Status.ABSTAINED and "unavailable" in r.abstention_reason


def test_llm_tool_call_round_trip_uses_backend_numbers(make_copilot):
    first = {"claims": [], "tool_calls": [{"name": "flex_summary", "arguments": {"fuel": "Heptane"}}]}

    class Second(ScriptedProvider):
        def complete(self, system, payload):
            self.payloads.append(payload)
            if len(self.payloads) == 1:
                return first
            tid = payload["tool_results"][-1]["tool_result_id"]
            return out(
                {
                    "text": "Backend descriptive summary returned.",
                    "evidence_type": "direct",
                    "citations": [],
                    "tool_result_ids": [tid],
                }
            )

    p = Second()
    r = ask(make_copilot(p), "Tell me about heptane droplets in FLEX.")
    assert r.status is Status.ANSWERED and r.tool_results[-1].tool == "flex_summary" and r.tool_results[-1].ok
    assert r.tool_results[-1].result["descriptive_exploratory_only"] is True


def test_non_whitelisted_or_invalid_tool_calls_are_refused(make_copilot):
    from app.rag.tools import run_tool

    assert not run_tool("T1", "os.system", {"cmd": "x"}).ok
    bad = run_tool("T2", "flex_summary", {"fuel": "Ethanol"})
    assert not bad.ok and "invalid arguments" in bad.error
    assert not run_tool("T3", "get_flex_run", {"experiment_id": "FLEX-999"}).ok


def test_user_supplied_droplet_series_runs_through_the_real_calculator(make_copilot):
    import numpy as np

    t = np.linspace(0, 4, 12)
    d = np.sqrt(4.0 - 0.5 * t)
    series = {
        "run_id": "r1",
        "regime": "flex_droplet",
        "fuel": "Heptane",
        "time_unit": "s",
        "diameter_unit": "mm",
        "window_selection": "test window",
        "time_s": t.tolist(),
        "diameter_mm": d.tolist(),
        "provenance": {"source_id": "PSI-69", "source_locator": "synthetic", "extraction_method": "test"},
    }
    r = ask(make_copilot(ExtractiveProvider()), HW, tool_inputs=ToolInputs(droplet_series=series))
    fit = next(t for t in r.tool_results if t.tool == "fit_burning_rate_constant")
    assert fit.ok and abs(fit.result["k_mm2_per_s"] - 0.5) < 1e-9
    series["provenance"]["source_id"] = "PSI-98"  # quarantined source is refused, as in the HTTP route
    r = ask(make_copilot(ExtractiveProvider()), HW, tool_inputs=ToolInputs(droplet_series=series))
    assert not next(t for t in r.tool_results if t.tool == "fit_burning_rate_constant").ok


def test_there_is_no_way_to_request_ineligible_evidence(make_copilot):
    import pytest
    from pydantic import ValidationError

    from app.rag.schemas import SearchFilter

    with pytest.raises(ValidationError):
        SearchFilter(include_quarantined=True)  # type: ignore[call-arg]
    r = ask(
        make_copilot(ExtractiveProvider()),
        "What flame spread rate was measured?",
        filters=SearchFilter(source_ids=["PSI-98", "PSI-25"]),
    )
    assert r.status is Status.ABSTAINED and not r.claims and not r.retrieved_chunk_ids
