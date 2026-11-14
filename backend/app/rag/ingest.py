"""Ingestion of ALLOW-LISTED, already-acquired sources into provenance-carrying chunks.

Nothing is ingested silently: every artifact hash is verified before parsing, and every chunk gets the
evidence eligibility of its source from app/rag/eligibility.py (shared registry + scientific decisions).
Sources that are not eligible (PSI-25 excluded, PSI-98 quarantined, the unregistered NASA/TP-2015-216046
captions) are indexed only so that they can be excluded explicitly and audited through the admin routes.
PSI-69 table rows are rendered from Data-Platform-compatible measurement facts (app/rag/measurements.py):
one statement per measurement, with missing and flagged values stated as such. Raw files are only read.
Only whitelisted narrative fields of PSI metadata are read (the raw JSON also holds contact e-mails).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from app.analysis import flex_run_level as fx
from app.domain.flex_schema import NASA_TP_FLEX, NASA_TP_FLEX_URL
from app.domain.regimes import CombustionRegime
from app.domain.sources import SourceRecord
from app.rag import ids
from app.rag.chunking import chunk_pages, content_hash, window_text
from app.rag.config import PROJECT_ROOT
from app.rag.eligibility import EligibilityPolicy
from app.rag.measurements import MeasurementFact, build_facts
from app.rag.schemas import CHUNKER_VERSION, Chunk, DocType, MeasurementRef

REGIME_BY_SOURCE = {
    "PSI-69": CombustionRegime.FLEX_DROPLET.value,
    "PSI-25": CombustionRegime.BASS_II_SOLID.value,
    "PSI-98": CombustionRegime.SAFFIRE_SPACECRAFT_SCALE.value,
}
TP_SOURCE_ID = "NASA-TP-2015-216046"
PSI_NARRATIVE_FIELDS = ("objective", "approach", "hypothesis", "researchImpacts")
PUBLICATIONS_PER_CHUNK = 6


class IngestError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _chunk(source: SourceRecord | None, **kw: object) -> Chunk:
    """Provisional chunk: `finalise` assigns chunk_id/chunk_index and the eligibility of the source."""
    text = str(kw["text"])
    base: dict[str, object] = {
        "chunk_id": "",
        "content_hash": content_hash(text),
        "source_url": source.source_url if source else "",
        "doi": source.doi if source else "",
        "license": source.license if source else "",
    }
    base.update(kw)
    if "artifact_id" not in base:
        base["artifact_id"] = ids.artifact_id(str(base["source_artifact_sha256"]), str(base["artifact_path"]))
    return Chunk.model_validate(base)


def finalise(chunks: list[Chunk], policy: EligibilityPolicy) -> list[Chunk]:
    """Assign document_chunks identity (artifact_id, chunker_version, chunk_index -> UUID) and eligibility."""
    counter: dict[str, int] = {}
    for c in chunks:
        idx = counter.get(c.artifact_id, 0)
        counter[c.artifact_id] = idx + 1
        c.chunk_index = idx
        c.chunk_id = ids.chunk_id(c.artifact_id, CHUNKER_VERSION, idx)
        d = policy.decision(c.source_id)
        c.verification_status = d.registry_status
        c.eligibility = d.eligibility.value
        c.usable_as_evidence = d.usable_as_evidence
        c.exclusion_reason = "" if d.usable_as_evidence else d.reason
        if not d.usable_as_evidence and "source_not_usable_as_evidence" not in c.quality_flags:
            c.quality_flags.append("source_not_usable_as_evidence")
    return chunks


# ------------------------------------------------------------------ PSI metadata narrative


def ingest_psi_metadata(root: Path, registry: dict[str, SourceRecord]) -> list[Chunk]:
    snap = json.loads((root / "data/metadata/psi_metadata_snapshot.json").read_text(encoding="utf-8"))
    out: list[Chunk] = []
    for sid, rec in snap["records"].items():
        src = registry.get(sid)
        data = (root / rec["raw_file_path"]).read_bytes()
        if _sha256(data) != rec["raw_sha256"]:
            raise IngestError(f"{sid}: PSI metadata hash mismatch; refusing to ingest")
        d = json.loads(data.decode("utf-8"))
        title = d.get("title") or ""
        acr = d.get("investigationAcronym") or sid
        common = {
            "source_id": sid,
            "source_title": f"{sid} {acr}: {title}".strip(),
            "regime": REGIME_BY_SOURCE.get(sid),
            "source_artifact_sha256": rec["raw_sha256"],
            "artifact_path": rec["raw_file_path"],
            "doc_type": DocType.PSI_METADATA,
        }
        summary = (
            f"{sid} ({acr}) {title}. Proposal title: {d.get('proposalTitle') or 'n/a'}. "
            f"Hardware: {d.get('experimentHardware') or 'n/a'}. Flight program: {d.get('flightProgram')}. "
            f"Managing centre: {d.get('managingNasaCenter')}. Investigation dates in PSI record: "
            f"{d.get('investigationStartDate')} to {d.get('investigationEndDate')}. DOI: {d.get('doi')}. "
            f"PSI licence: {d.get('licenseIdentifier')}. PSI record modified: {d.get('modifiedDate')}."
        )
        flags = ["psi_metadata_conflict_unresolved"] if sid == "PSI-98" else []
        out.append(
            _chunk(
                src,
                chunk_key=f"{sid}:meta:summary",
                locator={"section": "record summary"},
                locator_text=f"{sid} PSI investigation record, summary fields",
                text=summary,
                quality_flags=list(flags),
                **common,
            )
        )
        for fld in PSI_NARRATIVE_FIELDS:
            body = (d.get(fld) or "").strip()
            for i, w in enumerate(window_text(body), 1):
                out.append(
                    _chunk(
                        src,
                        chunk_key=f"{sid}:meta:{fld}:{i:02d}",
                        locator={"section": fld, "part": i},
                        locator_text=f"{sid} PSI investigation record, field '{fld}' (part {i})",
                        text=f"{sid} {acr} - {fld}: {w}",
                        quality_flags=list(flags),
                        **common,
                    )
                )
        pubs = d.get("publications") or []
        for gi in range(0, len(pubs), PUBLICATIONS_PER_CHUNK):
            grp = pubs[gi : gi + PUBLICATIONS_PER_CHUNK]
            lines = [
                f"[{gi + j + 1}] {p.get('authorList', '')}. {p.get('title', '')}"
                + (f" (DOI {p['doi']})" if p.get("doi") else "")
                for j, p in enumerate(grp)
            ]
            out.append(
                _chunk(
                    src,
                    chunk_key=f"{sid}:meta:publications:{gi // PUBLICATIONS_PER_CHUNK + 1:02d}",
                    locator={"section": "publications", "items": f"{gi + 1}-{gi + len(grp)}"},
                    locator_text=f"{sid} PSI record, publications {gi + 1}-{gi + len(grp)}",
                    text=f"{sid} {acr} - publications listed in the PSI record: " + " ".join(lines),
                    quality_flags=list(flags),
                    **common,
                )
            )
    return out


# ------------------------------------------------------------------ experimental tables


def _manifest(root: Path) -> dict[str, dict[str, str]]:
    with (root / "data/metadata/artifact_manifest.csv").open(encoding="utf-8", newline="") as fh:
        return {r["source_id"]: r for r in csv.DictReader(fh)}


def load_flex(root: Path) -> tuple[list[fx.FlexRun], dict[str, str], list[MeasurementFact]]:
    man = root / "data/metadata/artifact_manifest.csv"
    entry = fx.manifest_entry(man)
    runs, entry = fx.load_verified(root / entry["relative_path"], man)  # hash verified before parsing
    fx.attach_enrichment(runs, root / "data/derived/flex_enrichment_v1.csv")
    return runs, entry, build_facts(runs, entry)


def ingest_flex_table(
    root: Path, registry: dict[str, SourceRecord], runs_out: list | None = None
) -> list[Chunk]:
    runs, entry, facts = load_flex(root)
    if runs_out is not None:
        runs_out.extend(runs)
    by_run: dict[str, list[MeasurementFact]] = {}
    for f in facts:
        by_run.setdefault(f.run_id, []).append(f)
    src = registry.get("PSI-69")
    out: list[Chunk] = []
    for r in runs:
        run_key = ids.run_id("PSI-69", r.psi_row)
        mf = by_run[run_key]
        exp = mf[0].experiment_id
        head = (
            f"{exp} (FLEX test {r.flex_test_number}; PSI-69 row {r.psi_row}; identifier {r.identifier}; "
            f"run {run_key}): fuel {r.fuel}, test date {r.test_date} {r.test_time_gmt or 'time blank'} GMT, "
            f"test end {r.test_end or 'blank'}."
        )
        text = " ".join([head] + [f.sentence for f in mf])
        out.append(
            _chunk(
                src,
                chunk_key=f"PSI-69:row:{r.psi_row:03d}",
                source_id="PSI-69",
                source_title="PSI-69 FLEX experimental table",
                doc_type=DocType.TABLE_ROW,
                regime=CombustionRegime.FLEX_DROPLET.value,
                fuel_or_material=r.fuel,
                experiment_ids=[exp, r.identifier, r.record_key, run_key],
                locator={"table": "PSI-69 experimental table", "row": r.psi_row, "run_id": run_key},
                locator_text=f"PSI-69 experimental table (FLEX), row {r.psi_row}",
                text=text,
                source_artifact_sha256=entry["sha256"],
                artifact_path=entry["relative_path"],
                quality_flags=sorted(
                    set(r.row_flags) | {f"{f.variable}:{q}" for f in mf for q in f.quality_flags}
                ),
                measurements=[
                    MeasurementRef(
                        measurement_id=f.measurement_id,
                        run_id=f.run_id,
                        variable=f.variable,
                        unit=f.unit,
                        evidence_status=f.evidence_status.value,
                        original_value_text=f.original_value_text,
                        value=f.value,
                        quality_flags=list(f.quality_flags),
                        source_column=f.source_column,
                        source_locator=f.source_locator,
                        statement=f.sentence,
                    )
                    for f in mf
                ],
            )
        )
    return out


def ingest_generic_table(
    root: Path, sid: str, registry: dict[str, SourceRecord], material_col: str, id_col: str
) -> list[Chunk]:
    entry = _manifest(root)[sid]
    data = (root / entry["relative_path"]).read_bytes()
    if _sha256(data) != entry["sha256"]:
        raise IngestError(f"{sid}: experimental-table hash mismatch; refusing to ingest")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    header = [" ".join(h.split()) for h in rows[0]]
    src = registry.get(sid)
    out: list[Chunk] = []
    for n, row in enumerate(rows[1:], 1):
        cells = {h: " ".join(c.split()) for h, c in zip(header, row, strict=False) if c.strip()}
        if not cells:
            continue
        rid = cells.get(id_col, f"row{n}")
        body = "; ".join(f"{h}: {c}" for h, c in cells.items())
        text = f"{sid} experimental table row {n} ({rid}): {body}."
        out.append(
            _chunk(
                src,
                chunk_key=f"{sid}:row:{n:03d}",
                source_id=sid,
                source_title=f"{sid} experimental table",
                doc_type=DocType.TABLE_ROW,
                regime=REGIME_BY_SOURCE[sid],
                fuel_or_material=cells.get(material_col),
                experiment_ids=[rid],
                locator={"table": f"{sid} experimental table", "row": n},
                locator_text=f"{sid} experimental table, row {n}",
                text=text,
                source_artifact_sha256=entry["sha256"],
                artifact_path=entry["relative_path"],
            )
        )
    return out


# ------------------------------------------------------------------ NASA/TP figure captions


def ingest_tp_captions(root: Path, flex_runs: list[fx.FlexRun]) -> list[Chunk]:
    """NASA/TP-2015-216046 captions as extracted by pypdf for the approved v0.2.0 enrichment.

    The report is NOT in the source registry, so its eligibility resolves to UNREGISTERED and these
    chunks are never evidence. The artifact is the derived caption file actually read (hash recorded);
    the hash of the original PDF is kept in the locator.
    """
    rel = "data/derived/flex_enrichment_v1_captions.json"
    data = (root / rel).read_bytes()
    d = json.loads(data.decode("utf-8"))
    sha = _sha256(data)
    by_num = {r.flex_test_number: r for r in flex_runs}
    out: list[Chunk] = []
    for key, c in d["captions"].items():
        r = by_num.get(int(key.split("-")[1]))
        ident = f" (identifier {r.identifier}, {r.fuel})" if r else ""
        text = f"{key}{ident} - NASA/TP-2015-216046 Appendix B, Figure {c['figure']} caption: {c['caption']}"
        out.append(
            _chunk(
                None,
                chunk_key=f"{TP_SOURCE_ID}:caption:{key}",
                source_id=TP_SOURCE_ID,
                source_title=NASA_TP_FLEX,
                source_url=NASA_TP_FLEX_URL,
                license=(
                    "NTRS 20150023456 copyright field 'Public Use Permitted' "
                    "(not yet recorded in the registry)"
                ),
                doc_type=DocType.REPORT_CAPTION,
                regime=CombustionRegime.FLEX_DROPLET.value,
                fuel_or_material=r.fuel if r else None,
                experiment_ids=[key] + ([r.identifier, r.record_key] if r else []),
                locator={
                    "appendix": "B",
                    "figure": c["figure"],
                    "pdf_page": c["pdf_page"],
                    "pdf_sha256": d["source"]["pdf_sha256"],
                },
                locator_text=f"NASA/TP-2015-216046, Appendix B, Fig. {c['figure']} (PDF p. {c['pdf_page']})",
                text=text,
                source_artifact_sha256=sha,
                artifact_path=rel,
                quality_flags=["pypdf_text_extraction_not_visually_verified"]
                + ([] if r else ["no_matching_psi_row"]),
            )
        )
    return out


# ------------------------------------------------------------------ generic documents (adapter)


def read_pdf_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader  # optional dependency: pip install '.[rag]'
    except ImportError as exc:  # pragma: no cover - exercised only without pypdf
        raise IngestError("PDF ingestion needs the optional 'pypdf' package (pip install .[rag])") from exc
    return [(i, (p.extract_text() or "")) for i, p in enumerate(PdfReader(str(path)).pages, 1)]


def ingest_text_document(
    path: Path, source: SourceRecord, *, regime: str | None = None, experiment_ids: list[str] | None = None
) -> list[Chunk]:
    """Adapter for NEW documents (PDF / markdown / text). The source must be a registered, usable one."""
    if not source.usable_as_evidence:
        raise IngestError(
            f"{source.source_id} is {source.verification_status.value}; not ingestible as evidence"
        )
    data = path.read_bytes()
    if source.sha256 and _sha256(data) != source.sha256:
        raise IngestError(f"{source.source_id}: file hash does not match the registry; refusing to ingest")
    pages = read_pdf_pages(path) if path.suffix.lower() == ".pdf" else [(1, data.decode("utf-8"))]
    out: list[Chunk] = []
    for n, (page, section, text) in enumerate(chunk_pages(pages), 1):
        loc = f"{source.source_title}, p. {page}" + (f", section '{section}'" if section else "")
        out.append(
            _chunk(
                source,
                chunk_key=f"{source.source_id}:doc:{n:04d}",
                source_id=source.source_id,
                source_title=source.source_title,
                doc_type=DocType.TEXT_DOCUMENT,
                regime=regime,
                experiment_ids=experiment_ids or [],
                locator={"page": page, "section": section or None},
                locator_text=loc,
                text=text,
                source_artifact_sha256=_sha256(data),
                artifact_path=source.raw_file_path or path.name,
            )
        )
    return out


# ------------------------------------------------------------------ entry point


def build_corpus(root: Path = PROJECT_ROOT) -> list[Chunk]:
    policy = EligibilityPolicy(root)
    registry = policy.registry
    runs: list[fx.FlexRun] = []
    chunks = ingest_psi_metadata(root, registry)
    chunks += ingest_flex_table(root, registry, runs)
    chunks += ingest_generic_table(root, "PSI-25", registry, "Fuel Sample Material", "Test #")
    chunks += ingest_generic_table(root, "PSI-98", registry, "Material", "Sample Number")
    chunks += ingest_tp_captions(root, runs)
    finalise(chunks, policy)
    for attr in ("chunk_id", "chunk_key"):
        vals = [getattr(c, attr) for c in chunks]
        if len(vals) != len(set(vals)):
            raise IngestError(f"duplicate {attr} produced by ingestion")
    return chunks
