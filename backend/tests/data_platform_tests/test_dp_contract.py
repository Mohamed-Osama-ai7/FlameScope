"""Integration contract (docs/15_integration_contract.md): doc/code sync, error contract, scenarios 1-5,
and the guarded analysis-result writer."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid

import pytest
from sqlalchemy import func, select

from app.data_platform import loader
from app.data_platform.analysis_store import AnalysisInputRejected, record_analysis_result
from app.data_platform.api import router
from app.data_platform.db import session_factory
from app.data_platform.extract_flex import parse_locator
from app.data_platform.models import AnalysisResult, AnalysisResultInput, Measurement

from .conftest import PROJECT_ROOT, RAW_PSI69

V1 = "/api/v1"
CONTRACT = PROJECT_ROOT / "docs" / "15_integration_contract.md"
K = "burning_rate_constant_mm2_s"


def _routes() -> set[str]:
    return {f"GET {V1}{r.path}" for r in router.routes}  # type: ignore[attr-defined]


# ------------------------------------------------------------------ contract stays true to the code


def test_contract_endpoint_table_matches_the_router():
    documented = set(re.findall(r"^\| \d+ \| `(GET /api/v1/[^`]+)` \|", CONTRACT.read_text("utf-8"), re.M))
    assert documented == _routes()
    assert len(documented) == 11


def test_openapi_declares_error_responses(client):
    paths = client.get("/openapi.json").json()["paths"]
    for route in _routes():
        responses = paths[route.split(" ", 1)[1]]["get"]["responses"]
        assert "503" in responses, route
        if "{" in route:
            assert "404" in responses, route


def test_measurements_default_is_usable_only(client):
    params = {
        p["name"]: p
        for p in client.get("/openapi.json").json()["paths"][f"{V1}/measurements"]["get"]["parameters"]
    }
    assert params["usable_only"]["schema"]["default"] is True


def test_configured_but_unreachable_database_is_503(monkeypatch):
    from fastapi.testclient import TestClient

    from app.data_platform.db import get_engine
    from app.data_platform.settings import DATABASE_URL_ENV
    from app.main import app

    monkeypatch.setenv(DATABASE_URL_ENV, "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none")
    get_engine.cache_clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"{V1}/runs")
    assert r.status_code == 503 and "unreachable" in r.json()["detail"]


# ------------------------------------------------------------------ scenarios 1-5 (Part C)


def _first_k(db_client) -> dict:
    page = db_client.get(f"{V1}/measurements", params={"variable": K, "limit": 1}).json()
    assert page["total"] == 258
    return page["items"][0]


def test_s1_retrieve_valid_measurement(db_client):
    m = _first_k(db_client)
    assert m["usable_for_analysis"] is True and isinstance(m["value"], float)
    assert db_client.get(f"{V1}/measurements/{m['measurement_id']}").json() == m


def test_s2_provenance(db_client):
    m = _first_k(db_client)
    p = db_client.get(f"{V1}/measurements/{m['measurement_id']}/provenance").json()
    assert p["measurement"] == m
    assert p["run"]["run_id"] == m["run_id"] and p["source_cell"]["source_locator"] == m["source_locator"]
    assert (
        p["investigation"]["investigation_id"]
        == p["run"]["investigation_id"]
        == p["artifact"]["investigation_id"]
    )
    assert p["investigation"]["registry_status"] in {"ACQUIRED", "VERIFIED"}
    assert p["artifact"]["sha256"] in p["how_to_verify"]


@pytest.mark.skipif(not RAW_PSI69.exists(), reason="raw PSI-69 table not present (gitignored)")
def test_s3_verify_against_source_bytes(db_client):
    """The citation check of Part B.5, done exactly as a RAG auditor would, using only API output."""
    m = _first_k(db_client)
    p = db_client.get(f"{V1}/measurements/{m['measurement_id']}/provenance").json()
    data = (PROJECT_ROOT / p["artifact"]["relative_path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == p["artifact"]["sha256"]
    assert len(data) == p["artifact"]["byte_size"]
    lines = list(csv.reader(io.StringIO(data.decode(p["artifact"]["text_encoding"]))))
    loc = parse_locator(m["source_locator"])
    cell = lines[int(loc["csv_line"]) - 1][lines[0].index(loc["column"])]
    assert cell == m["original_value_text"] == p["source_cell"]["original_value_text"]
    assert float(cell) == m["value"]


def _ids(session, **where) -> list[uuid.UUID]:
    stmt = select(Measurement.measurement_id)
    for k, v in where.items():
        stmt = stmt.where(getattr(Measurement, k) == v)
    return list(session.scalars(stmt.order_by(Measurement.measurement_id)))


def test_s4_invalid_inputs_rejected(loaded_sqlite):
    with session_factory(loaded_sqlite)() as s:
        (bad_pressure,) = _ids(s, run_id="PSI-69-r114", variable_name="ambient_pressure")
        missing = _ids(s, value_status="missing")[0]
        good = _ids(s, run_id="PSI-69-r001", variable_name=K)[0]
        with pytest.raises(AnalysisInputRejected) as exc:
            record_analysis_result(
                s, method_id="t", method_version="1", output={}, computable=True,
                input_measurement_ids=[good, bad_pressure, missing, uuid.uuid4()],
            )  # fmt: skip
        problems = exc.value.problems
        assert "invalid_nonpositive_pressure" in problems[str(bad_pressure)]
        assert "no numeric value" in problems[str(missing)]
        assert any(v == "unknown measurement" for v in problems.values())
        assert str(good) not in problems
        with pytest.raises(AnalysisInputRejected, match="at least one input"):
            record_analysis_result(s, method_id="t", method_version="1", output={}, computable=True,
                                   input_measurement_ids=[])  # fmt: skip
        with pytest.raises(AnalysisInputRejected, match="abstention_reason"):
            record_analysis_result(s, method_id="t", method_version="1", output={}, computable=False,
                                   input_measurement_ids=[good])  # fmt: skip
        assert s.scalar(select(func.count()).select_from(AnalysisResult)) == 0


def test_valid_result_keeps_its_input_references(loaded_sqlite):
    with session_factory(loaded_sqlite)() as s:
        inputs = _ids(s, run_id="PSI-69-r001", usable_for_analysis=True)
        result = record_analysis_result(
            s, method_id="describe", method_version="1", run_id="PSI-69-r001",
            output={"n": len(inputs)}, computable=True, input_measurement_ids=[*inputs, inputs[0]],
        )  # fmt: skip
        s.commit()
        stored = set(
            s.scalars(
                select(AnalysisResultInput.measurement_id).where(
                    AnalysisResultInput.result_id == result.result_id
                )
            )
        )
        assert stored == set(inputs)  # duplicates collapsed, nothing lost


def test_s5_withdrawn_and_quarantined_rejected(loaded_sqlite, db_client, monkeypatch):
    from app.domain.sources import VerificationStatus

    real = loader.load_registry
    monkeypatch.setattr(
        loader,
        "load_registry",
        lambda path: [
            r.model_copy(update={"verification_status": VerificationStatus.QUARANTINED})
            if r.source_id == "PSI-69"
            else r
            for r in real(path)
        ],
    )
    with session_factory(loaded_sqlite)() as s:
        loader.load_all(s, PROJECT_ROOT, ["PSI-69", "PSI-98"])
        ids = _ids(s, run_id="PSI-69-r001", variable_name=K)
        with pytest.raises(AnalysisInputRejected, match="QUARANTINED"):
            record_analysis_result(s, method_id="t", method_version="1", output={}, computable=True,
                                   input_measurement_ids=ids)  # fmt: skip
    assert db_client.get(f"{V1}/measurements").json()["total"] == 0
    hidden = db_client.get(f"{V1}/measurements", params={"usable_only": False, "limit": 1}).json()["items"][0]
    assert "source_withdrawn" in hidden["quality_flags"] and hidden["usable_for_analysis"] is False
    assert db_client.get(f"{V1}/investigations/PSI-98").status_code == 404  # quarantined: never loaded
