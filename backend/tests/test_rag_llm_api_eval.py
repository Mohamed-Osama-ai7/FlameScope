import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.config import PROJECT_ROOT, RagConfig
from app.rag.evaluation import _ndcg, load_questions, retrieval_metrics, verify_gold
from app.rag.llm import LLMUnavailableError, OpenAICompatProvider, make_provider
from app.rag.service import reset_service

# ------------------------------------------------------------------ LLM provider (no network: mock transport)


def _cfg(**kw):
    return replace(
        RagConfig.from_env(),
        llm_provider="openai_compat",
        llm_api_key="sk-secret-test",
        llm_model="test-model",
        llm_base_url="https://llm.example/v1",
        **kw,
    )


def test_openai_compat_provider_posts_json_with_bearer_and_parses_output():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        content = json.dumps({"answer": "x", "claims": [], "abstain": True, "abstain_reason": "r"})
        return httpx.Response(200, json={"choices": [{"message": {"content": f"```json\n{content}\n```"}}]})

    p = OpenAICompatProvider(_cfg(), httpx.Client(transport=httpx.MockTransport(handler)))
    res = p.complete("sys", {"question": "q"})
    assert res["abstain"] is True and seen["url"] == "https://llm.example/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret-test" and seen["body"]["temperature"] == 0
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_provider_errors_never_leak_the_key():
    def boom(req):
        return httpx.Response(500, text="server error sk-secret-test")

    p = OpenAICompatProvider(_cfg(), httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(LLMUnavailableError) as e:
        p.complete("s", {})
    assert "sk-secret-test" not in str(e.value)
    with pytest.raises(LLMUnavailableError):
        OpenAICompatProvider(replace(_cfg(), llm_api_key=""))
    with pytest.raises(LLMUnavailableError):
        make_provider(replace(_cfg(), llm_provider="nope"))


# ------------------------------------------------------------------ API


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLAMESCOPE_DENSE_BACKEND", "hashing")
    monkeypatch.setenv("FLAMESCOPE_LLM_PROVIDER", "extractive")
    monkeypatch.setenv("FLAMESCOPE_LLM_API_KEY", "sk-should-never-be-returned")
    monkeypatch.setenv("FLAMESCOPE_RAG_CACHE", str(tmp_path))
    reset_service()
    yield TestClient(app)
    reset_service()


def test_api_status_search_chunk_and_tools(client):
    s = client.get("/api/v1/rag/status").json()
    assert s["chunks"] > 700 and s["usable_chunks"] < s["chunks"] and s["llm_key_configured"] is True
    assert "sk-should-never-be-returned" not in json.dumps(s)
    r = client.post("/api/v1/rag/search", json={"query": "BASS-II hardware", "top_k": 5, "mode": "bm25"})
    assert r.status_code == 200 and all(h["chunk"]["source_id"] == "PSI-69" for h in r.json()["hits"])
    r = client.post("/api/v1/rag/search", json={"query": "FLEX droplet hardware", "top_k": 3})
    cid = r.json()["hits"][0]["chunk"]["chunk_id"]
    assert client.get(f"/api/v1/rag/chunks/{cid}").json()["chunk_id"] == cid
    assert client.get("/api/v1/rag/chunks/PSI-69:row:070").status_code == 200  # readable key resolves
    assert client.get("/api/v1/rag/chunks/NOPE:1").status_code == 404
    assert {t["name"] for t in client.get("/api/v1/rag/tools").json()} >= {
        "validate_comparison",
        "get_flex_run",
    }
    assert client.post("/api/v1/rag/search", json={"query": "", "top_k": 3}).status_code == 422
    f = {"query": "burning rate", "filters": {"regimes": ["bass_ii_solid"], "doc_types": ["table_row"]}}
    assert client.post("/api/v1/rag/search", json=f).json()["hits"] == []  # excluded regime data


def test_api_copilot_answers_abstains_and_blocks(client):
    a = client.post(
        "/api/v1/copilot/ask", json={"question": "Which hardware housed the FLEX droplet investigation?"}
    ).json()
    assert a["status"] == "answered" and a["source_eligibility"] == {"PSI-69": "PENDING_VERIFICATION"}
    assert "PSI-69:meta:summary" in {c["chunk_key"] for cl in a["claims"] for c in cl["citations"]}
    x = client.post(
        "/api/v1/copilot/ask", json={"question": "What hardware housed the BASS-II experiments?"}
    ).json()
    assert x["status"] == "abstained" and "ACQUIRED_BUT_EXCLUDED" in x["abstention_reason"]
    b = client.post(
        "/api/v1/copilot/ask", json={"question": "What flame spread rate was measured in SAFFIRE-I?"}
    ).json()
    assert b["status"] == "abstained" and b["claims"] == []
    c = client.post(
        "/api/v1/copilot/ask", json={"question": "Compare FLEX burning rate with BASS-II flame spread rate"}
    ).json()
    assert c["status"] == "comparison_blocked"
    assert client.post("/api/v1/copilot/ask", json={"question": "hi"}).status_code == 422


def test_existing_endpoints_are_unchanged(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/status").json()["scientific_dataset_loaded"] is False
    assert len(client.get("/api/v1/regimes").json()) == 3


def test_api_503_when_provider_is_misconfigured(monkeypatch, tmp_path):
    monkeypatch.setenv("FLAMESCOPE_LLM_PROVIDER", "openai_compat")
    monkeypatch.delenv("FLAMESCOPE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("FLAMESCOPE_RAG_CACHE", str(tmp_path))
    reset_service()
    r = TestClient(app).post("/api/v1/copilot/ask", json={"question": "What hardware housed BASS-II?"})
    reset_service()
    assert r.status_code == 503 and "FLAMESCOPE_LLM_API_KEY" in r.json()["detail"]


# ------------------------------------------------------------------ evaluation dataset and metrics


def test_eval_dataset_is_valid_and_backed_by_the_corpus(rag_chunks):
    qs = load_questions(PROJECT_ROOT / "backend/eval/rag_questions_v2.jsonl")
    assert 30 <= len(qs) <= 50
    assert verify_gold(qs, rag_chunks) == []
    assert len({q["id"] for q in qs}) == len(qs)
    assert {q["split"] for q in qs} == {"dev", "test"}
    assert sum(1 for q in qs if not q["answerable"]) >= 6


def test_gold_verification_catches_a_fabricated_label(rag_chunks):
    bad = [{"id": "X", "answerable": True, "gold_chunks": ["PSI-69:row:001"], "gold_quote": "K 7.77 mm^2/s"}]
    assert verify_gold(bad, rag_chunks)


def test_metric_math_and_bm25_regression_floor(retriever):
    assert _ndcg([1, 0, 0], 1, 10) == 1.0 and 0 < _ndcg([0, 1], 1, 10) < 1.0
    qs = load_questions(PROJECT_ROOT / "backend/eval/rag_questions_v2.jsonl")
    m = retrieval_metrics(retriever, qs, "bm25")
    # v2: 19 answerable (PSI-25 and most NASA/TP gold became refusals); measured R@10 1.0, MRR 0.947
    assert m["n"] == 19 and m["recall"]["@10"] >= 0.9 and 0 < m["mrr"] <= 1


def test_default_retrieval_is_bm25(monkeypatch, tmp_path):
    from app.rag.copilot import CopilotRequest
    from app.rag.schemas import SearchRequest

    assert SearchRequest(query="x").mode == "bm25" and CopilotRequest(question="xyz").mode == "bm25"
    monkeypatch.delenv("FLAMESCOPE_DENSE_BACKEND", raising=False)
    monkeypatch.delenv("FLAMESCOPE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("FLAMESCOPE_RAG_CACHE", str(tmp_path))
    assert RagConfig.from_env().dense_backend == "none"
    reset_service()
    c = TestClient(app)
    s = c.get("/api/v1/rag/status").json()
    r = c.post("/api/v1/rag/search", json={"query": "BASS-II hardware"}).json()
    reset_service()
    assert s["dense_backend"] == "none" and r["mode"] == "bm25" and r["warnings"] == []
