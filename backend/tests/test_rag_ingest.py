import json
import shutil
from pathlib import Path

import pytest

from app.domain.sources import SourceRecord, VerificationStatus
from app.rag import ids as ids_mod
from app.rag.chunking import chunk_pages, content_hash, split_sections, window_text
from app.rag.config import PROJECT_ROOT
from app.rag.ingest import IngestError, ingest_psi_metadata, ingest_text_document
from app.rag.schemas import CHUNKER_VERSION, INGESTION_VERSION, Chunk, DocType


def test_window_text_respects_limit_and_overlaps_one_sentence():
    text = " ".join(f"Sentence number {i} has exactly seven words here." for i in range(30))
    wins = window_text(text, max_words=40, overlap=1)
    assert len(wins) > 3
    assert all(len(w.split()) <= 40 + 8 for w in wins)  # a window may end with the carried-over sentence
    # overlap: the last sentence of window n opens window n+1
    last = wins[0].split(". ")[-1].rstrip(".")
    assert last in wins[1]
    assert window_text("") == []


def test_sections_and_pages_are_never_crossed():
    pages = [(1, "# A\nFirst body sentence. Second one.\n## B\nNested body."), (2, "# C\nPage two body.")]
    chunks = chunk_pages(pages)
    assert {(p, s) for p, s, _ in chunks} == {(1, "A"), (1, "A > B"), (2, "C")}
    assert all("Page two" not in t for p, _, t in chunks if p == 1)
    assert split_sections("no heading text") == [("", "no heading text")]


def test_every_chunk_carries_full_provenance(rag_chunks: list[Chunk]):
    assert len(rag_chunks) > 700
    ids = [c.chunk_id for c in rag_chunks]
    assert len(ids) == len(set(ids)) and len({c.chunk_key for c in rag_chunks}) == len(ids)
    for c in rag_chunks:
        assert c.source_id and c.source_title and c.locator_text and c.locator
        assert c.content_hash == content_hash(c.text)
        assert c.ingestion_version == INGESTION_VERSION and c.chunker_version == CHUNKER_VERSION
        assert c.source_artifact_sha256, c.chunk_id
        assert c.regime is not None
        assert c.chunk_id == ids_mod.chunk_id(c.artifact_id, c.chunker_version, c.chunk_index)
        assert c.artifact_id == ids_mod.artifact_id(c.source_artifact_sha256, c.artifact_path)
        assert c.eligibility
        if c.usable_as_evidence:
            assert c.source_url and c.eligibility in {"VERIFIED_ELIGIBLE", "PENDING_VERIFICATION"}
        else:
            assert c.exclusion_reason
    nasa = [c for c in rag_chunks if c.doc_type is DocType.PSI_METADATA]
    assert all(c.doi and c.license == "CC0-1.0" for c in nasa if c.source_id != "PSI-98")


def test_corpus_counts_match_the_acquired_sources(rag_chunks: list[Chunk]):
    rows = [c for c in rag_chunks if c.chunk_key.startswith("PSI-69:row:")]
    caps = [c for c in rag_chunks if c.doc_type is DocType.REPORT_CAPTION]
    assert len(rows) == 274  # all PSI-69 rows, duplicates included
    assert len(caps) == 276  # NASA/TP-2015-216046 Appendix B captions
    keys = {c.chunk_key: c for c in rows}
    a, b = keys["PSI-69:row:070"], keys["PSI-69:row:073"]
    assert "193F001" in a.experiment_ids and "193F001" in b.experiment_ids
    assert a.chunk_id != b.chunk_id and "duplicate_source_identifier" in a.quality_flags


def test_quarantined_psi98_is_ingested_but_never_usable(rag_chunks: list[Chunk]):
    psi98 = [c for c in rag_chunks if c.source_id == "PSI-98"]
    assert psi98 and all(not c.usable_as_evidence for c in psi98)
    assert all("source_not_usable_as_evidence" in c.quality_flags for c in psi98)
    assert any("psi_metadata_conflict_unresolved" in c.quality_flags for c in psi98)


def test_no_contact_details_are_ingested(rag_chunks: list[Chunk]):
    blob = " ".join(c.text for c in rag_chunks)
    assert "@" not in blob.replace("@@", "")  # raw PSI JSON contains contact e-mails; they must not be read


def test_hash_mismatch_refuses_ingestion(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "data/metadata").mkdir(parents=True)
    (root / "data/raw/PSI-69/metadata").mkdir(parents=True)
    snap = json.loads((PROJECT_ROOT / "data/metadata/psi_metadata_snapshot.json").read_text(encoding="utf-8"))
    snap["records"] = {"PSI-69": snap["records"]["PSI-69"]}
    (root / "data/metadata/psi_metadata_snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    src = PROJECT_ROOT / snap["records"]["PSI-69"]["raw_file_path"]
    dst = root / snap["records"]["PSI-69"]["raw_file_path"]
    shutil.copy(src, dst)
    dst.write_bytes(dst.read_bytes() + b" ")  # tamper
    with pytest.raises(IngestError, match="hash mismatch"):
        ingest_psi_metadata(root, {})


def _source(status: VerificationStatus, sha: str) -> SourceRecord:
    return SourceRecord(
        source_id="DOC-TEST",
        source_title="Test report",
        source_type="TEST",
        official_challenge_resource=False,
        source_url="https://example.org/r",
        doi="10.0/x",
        retrieved_at_utc="2026-01-01T00:00:00Z",
        license="CC0-1.0",
        raw_file_path="r.md",
        sha256=sha,
        verification_status=status,
    )


def test_generic_document_adapter_keeps_page_and_section_and_checks_hash(tmp_path: Path):
    doc = tmp_path / "r.md"
    doc.write_text(
        "# Intro\nAlpha sentence one. Alpha sentence two.\n# Results\nBeta result text.", encoding="utf-8"
    )
    sha = content_hash("")  # placeholder; real hash below
    import hashlib

    sha = hashlib.sha256(doc.read_bytes()).hexdigest()
    chunks = ingest_text_document(doc, _source(VerificationStatus.ACQUIRED, sha), regime="flex_droplet")
    assert [c.locator["section"] for c in chunks] == ["Intro", "Results"]
    assert all(c.locator["page"] == 1 and c.source_artifact_sha256 == sha for c in chunks)
    with pytest.raises(IngestError, match="does not match"):
        ingest_text_document(doc, _source(VerificationStatus.ACQUIRED, "0" * 64))
    with pytest.raises(IngestError, match="not ingestible"):
        ingest_text_document(doc, _source(VerificationStatus.QUARANTINED, ""))
