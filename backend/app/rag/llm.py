"""Replaceable LLM providers. The Copilot only depends on ``LLMProvider.complete``.

* ``extractive``    - deterministic, offline, no model: answers by quoting the best-matching sentences of the
  retrieved evidence. Always available; used by tests and as the safe default.
* ``openai_compat`` - any OpenAI-compatible /chat/completions endpoint (OpenAI, Azure-compatible gateways,
  vLLM, Ollama ...) configured only by environment variables. No key is hard-coded or logged.
Whatever a provider returns is untrusted: citations.py validates it before anything reaches the user.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Protocol

import httpx

from app.rag.bm25 import core_tokens
from app.rag.chunking import split_sentences
from app.rag.config import RagConfig
from app.rag.query_analysis import GENERIC


class LLMUnavailableError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON object: {answer, claims:[{text, evidence_type, citations:[{chunk_id, quote}],
        tool_result_ids}], abstain, abstain_reason, tool_calls:[{name, arguments}]}."""
        ...


SYSTEM_PROMPT = """You are the FlameScope Scientific Copilot for microgravity-combustion evidence.
Rules (violations are detected and discarded):
1. Use ONLY the supplied evidence chunks and tool results. If they do not answer the question, set
   "abstain": true and explain what is missing. Never use outside knowledge, never invent measurements,
   conditions, citations or NASA findings.
2. Every claim must cite one or more chunk_ids with a VERBATIM quote from that chunk, or reference a
   tool_result_id. Numbers must be copied from a cited chunk or a tool result; never calculate numbers.
3. Label each claim "direct" (same regime/fuel/experiment as asked), "analogous" (different regime, fuel
   or conditions) or "missing" (what could not be found).
4. Never compare different combustion regimes as if directly comparable unless a validate_comparison tool
   result with shared_axis_allowed=true is provided.
5. If tools are needed, return {"tool_calls":[{"name":..., "arguments":{...}}]} using only the whitelisted
   tools in "tools". Respond with a single JSON object and nothing else."""


class ExtractiveProvider:
    name = "extractive (deterministic, no LLM)"

    def complete(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        q = set(core_tokens(payload["question"])) - GENERIC  # "record", "state"... say nothing
        evidence = payload["evidence"][:3]
        # Weight query terms by how rare they are among the candidate sentences: terms that occur in every
        # sentence (the entity named in the question) discriminate nothing; the asked-about field does.
        sent_sets = [
            set(core_tokens(s)) for ev in evidence for s in (split_sentences(ev["text"]) or [ev["text"]])
        ]
        n = max(1, len(sent_sets))
        weight = {t: math.log(1 + n / (1 + sum(t in s for s in sent_sets))) for t in q}

        def score(sentence: str) -> float:
            return sum(weight[t] for t in q & set(core_tokens(sentence)))

        claims: list[dict[str, Any]] = []
        for ev in evidence:
            sents = split_sentences(ev["text"]) or [ev["text"]]
            best = max(sents, key=lambda s: (score(s), -len(s)))
            if not q & set(core_tokens(best)):
                continue
            claims.append(
                {
                    "text": best,
                    "evidence_type": "direct",
                    "citations": [{"chunk_id": ev["chunk_id"], "quote": best}],
                    "tool_result_ids": [],
                }
            )
        for tr in payload.get("tool_results", []):
            # measurement lookups are answered by the backend's own measurement statements (copilot.py)
            if tr["ok"] and tr["tool"] != "get_flex_run":
                claims.append(
                    {
                        "text": f"Backend tool '{tr['tool']}' returned a result (see tool_results).",
                        "evidence_type": "direct",
                        "citations": [],
                        "tool_result_ids": [tr["tool_result_id"]],
                    }
                )
        if not claims:
            return {
                "answer": "",
                "claims": [],
                "abstain": True,
                "abstain_reason": "no retrieved sentence matches the question",
                "tool_calls": [],
            }
        return {
            "answer": " ".join(c["text"] for c in claims),
            "claims": claims,
            "abstain": False,
            "abstain_reason": None,
            "tool_calls": [],
        }


class OpenAICompatProvider:
    def __init__(self, cfg: RagConfig, client: httpx.Client | None = None) -> None:
        if not cfg.llm_api_key or not cfg.llm_model:
            raise LLMUnavailableError("FLAMESCOPE_LLM_API_KEY and FLAMESCOPE_LLM_MODEL must be set")
        self.name = f"openai_compat:{cfg.llm_model}"
        self._cfg = cfg
        self._client = client or httpx.Client(timeout=cfg.llm_timeout_s)

    def complete(self, system: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self._cfg.llm_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        try:
            r = self._client.post(
                self._cfg.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self._cfg.llm_api_key}"},
                json=body,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # never include headers/keys in the message
            raise LLMUnavailableError(f"LLM request failed: {type(exc).__name__}") from exc
        m = re.search(r"\{.*\}", content, re.S)
        try:
            out = json.loads(m.group(0) if m else content)
        except ValueError as exc:
            raise LLMUnavailableError("LLM did not return valid JSON") from exc
        if not isinstance(out, dict):
            raise LLMUnavailableError("LLM JSON is not an object")
        return out


def make_provider(cfg: RagConfig) -> LLMProvider:
    if cfg.llm_provider == "extractive":
        return ExtractiveProvider()
    if cfg.llm_provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    raise LLMUnavailableError(f"unknown FLAMESCOPE_LLM_PROVIDER '{cfg.llm_provider}'")
