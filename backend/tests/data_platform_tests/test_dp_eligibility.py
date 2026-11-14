"""Central evidence eligibility in the Data Platform (docs/22): loader, analysis store, API."""

from __future__ import annotations

import pytest

from app.data_platform import analysis_store, loader
from app.domain.eligibility import Eligibility, SourceDecision
from tests.data_platform_tests.conftest import PROJECT_ROOT


def test_loader_refuses_excluded_psi25_even_with_an_extractor(session, monkeypatch):
    called: list[str] = []

    class FakeExtractor:
        @staticmethod
        def extract(*args, **kwargs):  # pragma: no cover - must never run
            called.append("PSI-25")
            raise AssertionError("extractor must not be called for an excluded source")

    monkeypatch.setitem(loader.EXTRACTORS, "PSI-25", FakeExtractor)
    report = loader.load_all(session, PROJECT_ROOT, ["PSI-25"])
    res = {r.source_id: r for r in report.results}["PSI-25"]
    assert res.loaded is False and "ACQUIRED_BUT_EXCLUDED" in res.reason and not called


def test_analysis_store_rejects_inputs_from_a_source_that_becomes_ineligible(loaded_sqlite, monkeypatch):
    from sqlalchemy import select

    from app.data_platform.db import session_factory
    from app.data_platform.models import Measurement

    with session_factory(loaded_sqlite)() as s:
        mid = s.execute(
            select(Measurement.measurement_id).where(Measurement.usable_for_analysis.is_(True))
        ).scalar()

        class Excluded:
            def __init__(self, root):
                pass

            def decision(self, sid):
                return SourceDecision(sid, Eligibility.ACQUIRED_BUT_EXCLUDED, False, "ACQUIRED", "test")

        monkeypatch.setattr(analysis_store, "EligibilityPolicy", Excluded)
        with pytest.raises(analysis_store.AnalysisInputRejected) as exc:
            analysis_store.record_analysis_result(
                s, method_id="m", method_version="1", input_measurement_ids=[mid], output={}, computable=True
            )
        assert "ACQUIRED_BUT_EXCLUDED" in str(exc.value.problems)


def test_investigation_api_exposes_pending_verification(db_client):
    inv = db_client.get("/api/v1/investigations/PSI-69").json()
    assert inv["registry_status"] == "ACQUIRED" and inv["evidence_eligibility"] == "PENDING_VERIFICATION"
    m = db_client.get("/api/v1/measurements", params={"limit": 1}).json()["items"][0]
    prov = db_client.get(f"/api/v1/measurements/{m['measurement_id']}/provenance").json()
    assert prov["investigation"]["evidence_eligibility"] == "PENDING_VERIFICATION"
