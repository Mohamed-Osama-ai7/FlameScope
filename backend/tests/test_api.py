from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_status_does_not_claim_data_loaded():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scientific_dataset_loaded"] is False
    assert payload["official_challenge_resource_recorded"] is False


def test_sources_registry_is_available():
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    assert any(row["source_id"] == "CHALLENGE-RESOURCE-01" for row in response.json())


def test_regimes_are_distinct():
    regimes = {r["regime"] for r in client.get("/api/v1/regimes").json()}
    assert regimes == {"flex_droplet", "bass_ii_solid", "saffire_spacecraft_scale"}


def test_compare_endpoint_rejects_cross_regime_outcomes():
    payload = {
        "a": {"investigation_id": "PSI-69", "regime": "flex_droplet",
              "variable": "burning_rate_constant_mm2_s", "unit": "mm^2/s"},
        "b": {"investigation_id": "PSI-25", "regime": "bass_ii_solid",
              "variable": "flame_spread_rate", "unit": "mm/s"},
    }
    body = client.post("/api/v1/comparisons/validate", json=payload).json()
    assert body["classification"] == "not_comparable"


def test_methods_endpoint_exposes_method_cards():
    cards = client.get("/api/v1/methods").json()
    assert cards and all(c["references"] and c["validity_limits"] for c in cards)


SERIES = {
    "run_id": "x", "regime": "flex_droplet", "fuel": "test-fuel", "time_unit": "s",
    "diameter_unit": "mm", "window_selection": "test",
}
ENDPOINT = "/api/v1/analysis/droplet/burning-rate-constant"


def prov(source_id):
    return {"source_id": source_id, "source_locator": "test", "extraction_method": "test"}


def test_burning_rate_endpoint_requires_provenance():
    payload = {**SERIES, "time_s": [0, 1, 2], "diameter_mm": [2.0, 1.9, 1.8]}
    assert client.post(ENDPOINT, json=payload).status_code == 422


def test_burning_rate_endpoint_abstains_with_reason():
    payload = {**SERIES, "time_s": [0, 1], "diameter_mm": [2.0, 1.9], "provenance": prov("TEST")}
    body = client.post(ENDPOINT, json=payload).json()
    assert body["computable"] is False and body["abstention_reason"]


def test_burning_rate_endpoint_rejects_solid_regime():
    payload = {**SERIES, "regime": "bass_ii_solid", "time_s": [0, 1, 2],
               "diameter_mm": [2.0, 1.9, 1.8], "provenance": prov("TEST")}
    assert client.post(ENDPOINT, json=payload).status_code == 422


def test_quarantined_psi98_is_refused():
    payload = {**SERIES, "time_s": [0, 1, 2], "diameter_mm": [2.0, 1.9, 1.8],
               "provenance": prov("PSI-98")}
    r = client.post(ENDPOINT, json=payload)
    assert r.status_code == 422 and "QUARANTINED" in r.json()["detail"]


def test_candidate_source_not_yet_acquired_is_refused():
    payload = {**SERIES, "time_s": [0, 1, 2], "diameter_mm": [2.0, 1.9, 1.8],
               "provenance": prov("CHALLENGE-RESOURCE-01")}
    assert client.post(ENDPOINT, json=payload).status_code == 422


def test_unregistered_source_is_flagged_not_traceable():
    payload = {**SERIES, "time_s": [0, 1, 2], "diameter_mm": [2.0, 1.9, 1.75],
               "provenance": prov("TEST-ANALYTIC")}
    body = client.post(ENDPOINT, json=payload).json()
    assert body["computable"] is True
    assert any("not in the source registry" in w for w in body["warnings"])
