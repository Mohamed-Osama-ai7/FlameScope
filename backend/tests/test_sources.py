import pytest

from app.api.routes import REGISTRY_PATH
from app.domain.sources import (
    SourceRecord,
    VerificationStatus,
    load_registry,
    official_resource_recorded,
)

HASH = "a" * 64


def rec(**kw):
    base = dict(
        source_id="S",
        source_title="t",
        source_type="NASA_PSI",
        official_challenge_resource="YES",
        verification_status="CANDIDATE_ONLY",
    )
    base.update(kw)
    return SourceRecord.model_validate(base)


def test_repository_registry_is_valid():
    records = load_registry(REGISTRY_PATH)
    ids = {r.source_id for r in records}
    assert {"CHALLENGE-RESOURCE-01", "PSI-69", "PSI-25", "PSI-98"} <= ids


def test_acquired_requires_hash_license_and_path():
    with pytest.raises(ValueError):
        rec(verification_status="ACQUIRED", source_url="u", retrieved_at_utc="2026-11-13")


def test_official_flag_derived_from_registry_not_hardcoded():
    candidate = rec()
    assert not official_resource_recorded([candidate])
    acquired = rec(
        verification_status="ACQUIRED",
        source_url="https://example.invalid/resource",
        retrieved_at_utc="2026-11-13T00:00:00Z",
        license="CC0-1.0",
        raw_file_path="data/raw/S/file.csv",
        sha256=HASH,
    )
    assert acquired.verification_status is VerificationStatus.ACQUIRED
    assert official_resource_recorded([acquired])
    supplemental = acquired.model_copy(update={"official_challenge_resource": False})
    assert not official_resource_recorded([supplemental])


def test_invalid_yes_no_rejected():
    with pytest.raises(ValueError):
        rec(official_challenge_resource="maybe")


def test_psi98_quarantined_and_original_metadata_preserved():
    import json

    records = {r.source_id: r for r in load_registry(REGISTRY_PATH)}
    assert records["PSI-98"].verification_status is VerificationStatus.QUARANTINED
    assert not records["PSI-98"].usable_as_evidence
    snapshot = json.loads(
        (REGISTRY_PATH.parent / "psi_metadata_snapshot.json").read_text(encoding="utf-8")
    )
    fields = snapshot["records"]["PSI-98"]["fields"]
    # Verbatim NASA values are kept, not "corrected".
    assert fields["investigationStartDate"] == "03-02-2001"
    assert fields["proposalTitle"].startswith("Characterization of Smoke")
    assert any(d["source_id"] == "PSI-98" for d in snapshot["discrepancies"])
