"""Provenance-aware API: contract, filters, pagination, errors, and behaviour without a database."""

from __future__ import annotations

import pytest

from app.data_platform import api as dp_api
from app.data_platform.db import session_factory

V1 = "/api/v1"


# ------------------------------------------------------------------ without a database


@pytest.mark.parametrize(
    "path",
    [
        "/investigations",
        "/runs",
        "/runs/PSI-69-r001",
        "/measurements",
        "/variables",
        "/units",
        "/data-quality/PSI-69",
    ],
)
def test_data_endpoints_return_503_without_database(client, path):
    r = client.get(V1 + path)
    assert r.status_code == 503
    assert "FLAMESCOPE_DATABASE_URL" in r.json()["detail"]


def test_status_without_database_is_explicit(client):
    s = client.get(f"{V1}/data-platform/status").json()
    assert s["database_configured"] is False and s["database_reachable"] is False
    assert s["measurements"] == 0 and s["expected_schema_revision"] == "0001"
    assert client.get(f"{V1}/status").json()["scientific_dataset_loaded"] is False


def test_status_when_database_is_unreachable(client, monkeypatch):
    from app.data_platform.db import make_engine

    monkeypatch.setattr(
        dp_api,
        "get_engine",
        lambda: make_engine("postgresql+psycopg://nobody:nothing@127.0.0.1:1/none"),
    )
    s = client.get(f"{V1}/data-platform/status").json()
    assert s["database_configured"] is True and s["database_reachable"] is False


# ------------------------------------------------------------------ with the loaded database


def test_status_reports_loaded_official_data(db_client):
    s = db_client.get(f"{V1}/data-platform/status").json()
    assert s["database_reachable"] and s["schema_revision"] == s["expected_schema_revision"]
    assert s["investigations_loaded"] == ["PSI-69"] and s["official_challenge_resource_loaded"] is True
    assert (s["runs"], s["measurements"]) == (274, 2466)
    legacy = db_client.get(f"{V1}/status").json()
    assert legacy["scientific_dataset_loaded"] is True
    assert legacy["official_challenge_resource_recorded"] is True


def test_investigation_detail_exposes_artifact_hash_and_licence(db_client):
    assert [i["investigation_id"] for i in db_client.get(f"{V1}/investigations").json()] == ["PSI-69"]
    d = db_client.get(f"{V1}/investigations/PSI-69").json()
    assert d["research_area"] == "Combustion Science" and d["official_challenge_resource"] is True
    assert (d["run_count"], d["measurement_count"]) == (274, 2466)
    (art,) = d["artifacts"]
    assert art["sha256"] == "37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96"
    assert art["license_id"] == "CC0-1.0" and art["byte_size"] == 24776
    assert db_client.get(f"{V1}/investigations/PSI-25").status_code == 404


def test_runs_pagination_is_deterministic_and_complete(db_client):
    seen: list[str] = []
    for offset in range(0, 274, 100):
        page = db_client.get(f"{V1}/runs", params={"limit": 100, "offset": offset}).json()
        assert page["total"] == 274 and page["limit"] == 100 and page["offset"] == offset
        seen += [r["run_id"] for r in page["items"]]
    assert seen == [f"PSI-69-r{i:03d}" for i in range(1, 275)]
    assert db_client.get(f"{V1}/runs", params={"limit": 501}).status_code == 422


def test_run_filters(db_client):
    def total(**params):
        return db_client.get(f"{V1}/runs", params=params).json()["total"]

    assert total(fuel="Heptane") == 117 and total(fuel="Methanol") == 157
    assert total(end_mode="Extinction") == 186
    assert total(fuel="Heptane", end_mode="Extinction") + total(fuel="Methanol", end_mode="Extinction") == 186
    assert total(has_flag="duplicate_source_identifier") == 2
    assert total(combustion_regime="bass_ii_solid") == 0
    assert db_client.get(f"{V1}/runs", params={"has_flag": "x' OR 1=1 --"}).status_code == 422


def test_run_detail_contains_all_cells_with_provenance(db_client):
    r = db_client.get(f"{V1}/runs/PSI-69-r001").json()
    assert r["source_record_key"] == "PSI69-r001|FLEX-001|20CAL08|3/5/2009|17:22:03"
    assert len(r["measurements"]) == 9 and r["artifact"]["file_name"] == "PSI-69_Experimental table_FLEX.csv"
    k = next(m for m in r["measurements"] if m["variable_name"] == "burning_rate_constant_mm2_s")
    assert (k["value"], k["unit"], k["original_value_text"], k["measured_or_derived"]) == (
        0.52,
        "mm^2/s",
        "0.52",
        "report_value",
    )
    assert db_client.get(f"{V1}/runs/PSI-69-r999").status_code == 404


def test_measurement_filters(db_client):
    def total(**params):
        resp = db_client.get(f"{V1}/measurements", params=params)
        assert resp.status_code == 200, resp.text
        return resp.json()["total"]

    k = "burning_rate_constant_mm2_s"
    everything = {"usable_only": False}
    # Safe default: unusable cells (missing, invalid, withdrawn source) are excluded unless asked for.
    assert total() == 2354 and total(**everything) == 2466
    assert total(variable=k) == 258 and total(variable=k, **everything) == 274
    assert total(variable=k, value_status="missing") == 0
    assert total(variable=k, value_status="missing", **everything) == 16
    assert total(variable="ambient_pressure") == 273  # r114 (0 mmHg) excluded by default
    assert (
        total(variable="ambient_pressure", exclude_flag="invalid_nonpositive_pressure", **everything) == 273
    )
    assert total(value_status="approximate") == 2
    assert total(role="condition", **everything) == 274 * 6
    assert total(role="outcome", **everything) == 274 * 3
    assert total(investigation_id="PSI-69", run_id="PSI-69-r114", **everything) == 9
    assert db_client.get(f"{V1}/measurements", params={"variable": "nope"}).status_code == 404
    assert db_client.get(f"{V1}/measurements", params={"role": "result"}).status_code == 422


def test_missing_values_are_null_with_original_marker(db_client):
    items = db_client.get(
        f"{V1}/measurements",
        params={
            "variable": "extinction_diameter",
            "value_status": "missing",
            "usable_only": False,
            "limit": 1000,
        },
    ).json()["items"]
    assert items and all(m["value"] is None and not m["usable_for_analysis"] for m in items)
    assert {m["original_value_text"] for m in items} <= {"", "–"}


def test_provenance_resolves_to_source_bytes(db_client):
    m = db_client.get(f"{V1}/measurements", params={"run_id": "PSI-69-r223", "variable": "burn_time"}).json()
    (burn,) = m["items"]
    assert (burn["value"], burn["value_status"], burn["original_value_text"]) == (6.0, "approximate", "~6")
    p = db_client.get(f"{V1}/measurements/{burn['measurement_id']}/provenance").json()
    assert p["source_cell"]["source_column"] == "Burn time; s" and p["source_cell"]["source_row"] == 223
    assert p["artifact"]["sha256"] in p["how_to_verify"]
    assert p["extraction"]["extractor_version"] == "1.0.0"
    assert p["investigation"]["investigation_id"] == "PSI-69"
    assert p["run"]["run_id"] == "PSI-69-r223"
    assert (
        db_client.get(f"{V1}/measurements/00000000-0000-0000-0000-000000000000/provenance").status_code == 404
    )
    assert db_client.get(f"{V1}/measurements/not-a-uuid").status_code == 422


def test_vocabulary_and_quality_report(db_client):
    variables = {v["name"]: v for v in db_client.get(f"{V1}/variables").json()}
    assert variables["burn_time"]["defined_in"] == "app.data_platform.vocabulary"
    assert variables["burning_rate_constant_mm2_s"]["measurement_count"] == 274
    assert variables["flame_spread_rate"]["measurement_count"] == 0
    assert "mm^2/s" in {u["symbol"] for u in db_client.get(f"{V1}/units").json()}
    q = db_client.get(f"{V1}/data-quality/PSI-69").json()
    assert q["load_blocked"] is False and q["counts"].get("error_fail", 0) == 0
    checks = {c["check_name"]: c for c in q["checks"]}
    assert checks["missing_values"]["affected_count"] == 111
    assert checks["unit_dimension_matches_variable"]["outcome"] == "pass"
    assert db_client.get(f"{V1}/data-quality/PSI-98").status_code == 404


def test_openapi_lists_data_platform_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/api/v1/runs",
        "/api/v1/measurements/{measurement_id}/provenance",
        "/api/v1/data-platform/status",
    ):
        assert p in paths


def test_withdrawn_source_disappears_from_default_queries_and_status(db_client, loaded_sqlite):
    from sqlalchemy import update

    from app.data_platform.models import Investigation, Measurement

    with session_factory(loaded_sqlite)() as s:  # what loader._withdraw_loaded_source leaves behind
        s.execute(update(Investigation).values(registry_status="QUARANTINED"))
        s.execute(update(Measurement).values(usable_for_analysis=False))
        s.commit()
    assert db_client.get(f"{V1}/measurements").json()["total"] == 0
    status = db_client.get(f"{V1}/data-platform/status").json()
    assert status["investigations_loaded"] == [] and status["official_challenge_resource_loaded"] is False
