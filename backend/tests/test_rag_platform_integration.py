"""RAG x Scientific Data Platform integration (runs only where app.data_platform is importable).

On the RAG branch alone these tests skip. They are executed in a checkout that contains both branches'
code (see docs/14_rag_copilot.md section 9): a real Alembic-migrated SQLite database is loaded with the
platform loader, then the Copilot's citations are checked against it (contract docs/15, B.4/B.5).
"""

# ruff: noqa: I001  (import order differs depending on whether app.data_platform is present)
from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("app.data_platform")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, text  # noqa: E402

from app.data_platform import ids as dp_ids  # noqa: E402
from app.data_platform.db import get_engine, get_session, make_engine, session_factory  # noqa: E402
from app.data_platform.extract_flex import extract  # noqa: E402
from app.data_platform.loader import load_all  # noqa: E402
from app.domain.sources import find_source, load_registry  # noqa: E402
from app.rag import ids  # noqa: E402
from app.rag.config import PROJECT_ROOT, RagConfig  # noqa: E402
from app.rag.copilot import CopilotRequest, ScientificCopilot, Status  # noqa: E402
from app.rag.ingest import build_corpus, load_flex  # noqa: E402
from app.rag.llm import ExtractiveProvider  # noqa: E402
from app.rag.platform import sync_document_chunks  # noqa: E402
from app.rag.retriever import HybridRetriever  # noqa: E402

BACKEND = PROJECT_ROOT / "backend"
RAW = PROJECT_ROOT / "data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv"
SET_STATUS = "UPDATE investigations SET registry_status = :s WHERE investigation_id = 'PSI-69'"
pytestmark = pytest.mark.skipif(not RAW.exists(), reason="raw PSI-69 table not present (gitignored)")


@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Engine]]:
    url = f"sqlite:///{(tmp_path_factory.mktemp('dp') / 'flamescope.db').as_posix()}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = make_engine(url)
    with session_factory(engine)() as s:
        assert load_all(s, PROJECT_ROOT).ok
    yield url, engine
    engine.dispose()


@pytest.fixture(scope="module")
def copilot() -> ScientificCopilot:
    cfg = RagConfig.from_env()
    return ScientificCopilot(HybridRetriever(build_corpus(), cfg), ExtractiveProvider())


@pytest.fixture()
def platform_on(db, monkeypatch) -> Iterator[Engine]:
    monkeypatch.setenv("FLAMESCOPE_DATABASE_URL", db[0])
    get_engine.cache_clear()
    yield db[1]
    get_engine.cache_clear()


@pytest.fixture()
def api(db) -> Iterator[TestClient]:
    from app.data_platform import api as dp_api
    from app.main import app

    factory = session_factory(db[1])

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    old = dp_api.get_engine
    dp_api.get_engine = lambda: db[1]  # type: ignore[assignment]
    try:
        with TestClient(app) as c:
            yield c
    finally:
        dp_api.get_engine = old  # type: ignore[assignment]
        app.dependency_overrides.pop(get_session, None)


def ask(cop: ScientificCopilot, q: str):
    return cop.ask(CopilotRequest(question=q, mode="bm25"))


# ------------------------------------------------------------------ identity parity (no duplicate truth)


def test_ids_formulas_are_identical():
    assert ids.NAMESPACE == dp_ids.NAMESPACE
    assert ids.artifact_id("a" * 64, "x/y.csv") == str(dp_ids.artifact_id("a" * 64, "x/y.csv"))
    assert ids.measurement_id("b" * 64, 7, "Ambient pressure; mmHg") == str(
        dp_ids.measurement_id("b" * 64, 7, "Ambient pressure; mmHg")
    )
    assert ids.run_id("PSI-69", 7) == dp_ids.run_id("PSI-69", 7)


def test_every_rag_measurement_equals_the_platform_extraction():
    src = find_source(load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv"), "PSI-69")
    bundle = extract(PROJECT_ROOT, src, PROJECT_ROOT / "data/metadata/artifact_manifest.csv")
    dp = {str(m["measurement_id"]): m for m in bundle.measurements}
    rag = {f.measurement_id: f for f in load_flex(PROJECT_ROOT)[2]}
    assert set(dp) == set(rag) and len(rag) == 2466
    for mid, f in rag.items():
        m = dp[mid]
        assert (f.run_id, f.variable, f.unit, f.value_status, f.usable_for_analysis) == (
            m["run_id"],
            m["variable_name"],
            m["unit"],
            m["value_status"],
            m["usable_for_analysis"],
        ), mid
        assert f.value == m["value"] and f.original_value_text == m["original_value_text"]
        assert f.source_locator == m["source_locator"] and f.source_column == m["source_column"]
        assert set(m["quality_flags"]) <= set(f.quality_flags)  # RAG only adds row-level qualifiers
        assert str(m["artifact_id"]) == f.artifact_id


# ------------------------------------------------------------------ acceptance workflow


def test_full_workflow_source_to_measurement_provenance(platform_on, api, copilot):
    # NASA source -> validated artifact
    reg = find_source(load_registry(PROJECT_ROOT / "data/metadata/source_registry.csv"), "PSI-69")
    import hashlib

    assert hashlib.sha256(RAW.read_bytes()).hexdigest() == reg.sha256
    # -> Copilot answer from retrieval, numerical value from the backend measurement statement
    r = ask(copilot, "What was the initial droplet diameter in FLEX-070?")
    assert r.status is Status.ANSWERED and r.measurement_verification == "platform"
    cl = r.claims[0]
    ci = cl.citations[0]
    m = ci.measurements[0]
    assert cl.measurement_status == "CLEAN" and m.value == 4.67 and "4.67 mm" in cl.text
    assert ci.source_id == "PSI-69" and ci.eligibility == "PENDING_VERIFICATION"
    # -> database measurement (contract B.5 online check, through the platform API)
    got = api.get(f"/api/v1/measurements/{m.measurement_id}").json()
    assert got["usable_for_analysis"] is True and got["value"] == m.value and got["unit"] == m.unit
    prov = api.get(m.provenance).json()
    assert prov["investigation"]["registry_status"] in {"ACQUIRED", "VERIFIED"}
    assert prov["artifact"]["sha256"] == ci.source_artifact_sha256 == reg.sha256
    assert str(prov["artifact"]["artifact_id"]) == ci.artifact_id
    # -> the chunk is in document_chunks with the same id
    stats = sync_document_chunks(copilot.retriever.chunks, platform_on)
    assert stats["written"] >= 274
    with platform_on.connect() as c:
        row = c.execute(
            text("SELECT artifact_id, chunker_version FROM document_chunks WHERE chunk_id = :i"),
            {"i": uuid.UUID(ci.chunk_id).hex if platform_on.dialect.name == "sqlite" else ci.chunk_id},
        ).first()
    assert row is not None


def test_invalid_and_missing_values_agree_with_the_database(platform_on, copilot):
    r = ask(copilot, "What was the ambient pressure in FLEX test 114?")
    assert r.measurement_verification == "platform" and r.claims[0].measurement_status == "INVALID"
    assert not r.dropped_claims  # database confirms: value kept, usable_for_analysis false
    r = ask(copilot, "What was the extinction diameter in FLEX test 4?")
    assert r.measurement_verification == "platform" and r.claims[0].measurement_status == "MISSING"


def test_withdrawn_source_drops_numeric_claims(db, platform_on, copilot):
    with db[1].begin() as c:
        c.execute(text(SET_STATUS), {"s": "QUARANTINED"})
    try:
        r = ask(copilot, "What was the initial droplet diameter in FLEX-070?")
        assert not any(cl.measurement_ids for cl in r.claims)
        assert any("registry status is QUARANTINED" in x for d in r.dropped_claims for x in d.reasons)
    finally:
        with db[1].begin() as c:
            c.execute(text(SET_STATUS), {"s": "ACQUIRED"})


def test_database_unavailable_withdraws_numbers(monkeypatch, tmp_path, copilot):
    monkeypatch.setenv("FLAMESCOPE_DATABASE_URL", f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    get_engine.cache_clear()
    try:
        r = ask(copilot, "What was the initial droplet diameter in FLEX-070?")
    finally:
        get_engine.cache_clear()
    assert r.measurement_verification == "unavailable"
    assert not any(cl.measurement_ids for cl in r.claims)  # never a number without the database


def test_document_chunk_sync_is_idempotent_and_skips_ineligible(platform_on, copilot):
    a = sync_document_chunks(copilot.retriever.chunks, platform_on)
    b = sync_document_chunks(copilot.retriever.chunks, platform_on)
    assert a == b and a["skipped_ineligible"] == 428  # 139 PSI-25 + 13 PSI-98 + 276 NASA/TP
    with platform_on.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM document_chunks")).scalar_one()
    assert n == a["written"]


def test_rag_status_reports_the_platform_connection(platform_on, monkeypatch, tmp_path):
    from app.main import app
    from app.rag.service import reset_service

    monkeypatch.setenv("FLAMESCOPE_RAG_CACHE", str(tmp_path))
    reset_service()
    try:
        s = TestClient(app).get("/api/v1/rag/status").json()
    finally:
        reset_service()
    assert s["data_platform"]["connected"] is True
    assert Path(PROJECT_ROOT / "data/metadata/source_eligibility.csv").is_file()
