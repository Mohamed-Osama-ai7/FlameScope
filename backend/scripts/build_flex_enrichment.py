"""Build the provenance-linked FLEX enrichment layer from NASA/TP-2015-216046 (one-off, dev-only).

Usage (from repository root; needs pypdf, which is NOT a project dependency):
    python backend/scripts/build_flex_enrichment.py --pdf <path-to-NASA-TP-2015-216046.pdf> \
        --pypdf-path <dir containing pypdf>

The report PDF is not stored in the repository. Its SHA-256 is verified before use. Output:
    data/derived/flex_enrichment_v1.csv          one row per PSI-69 row (274), keyed by PSI row
    data/derived/flex_enrichment_v1_captions.json Appendix B caption text per FLEX test (public domain)

Nothing here modifies the raw PSI file. Every field records its source location; nothing is guessed:
a field the report does not state is left blank with status 'not_stated'.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PDF_SHA256 = "b4f6ca983e2792c33a0b92220a791a818f426bb635b94f7fd33dc8c9c471e79d"
REPORT = "NASA/TP-2015-216046"
ENRICHMENT_VERSION = "1"
PRINTED_PAGE_OFFSET = 6  # printed page = PDF page - 6 (e.g. Appendix A.1 PDF p.25 = printed p.19)

ROW_RE = re.compile(
    r"^FLEX\W{1,3}(\d{3})\s+(\S+)\s+(\S+)\s+(\S+)\s+(\w+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"
    r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\w+)",
    re.M,
)
CAPTION_RE = re.compile(r"Figure (\d+)\.?\W+Test FLEX\W+(\d{3})\.(.*?)(?=\n\s*\n\s*\n|=====PAGE)", re.S)
MATRIX_RE = re.compile(r"^(\d{3}) ([A-Z][a-z]{2,4}\.? \d{1,2}, ?\s*\d{4})(.*)$", re.M)


def num(v: str) -> float | None:
    v = v.replace("�", "").replace("–", "").replace("~", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def extract_pages(pdf: Path, pypdf_path: str | None) -> list[str]:
    if pypdf_path:
        sys.path.insert(0, pypdf_path)
    from pypdf import PdfReader  # noqa: PLC0415 - dev-only dependency

    return [p.extract_text() or "" for p in PdfReader(str(pdf)).pages]


def table_ix(pages: list[str]) -> list[dict[str, Any]]:
    rows = []
    for pno, text in enumerate(pages, start=1):
        if not 26 <= pno <= 34:  # Table IX spans PDF pages 26-34
            continue
        for m in ROW_RE.finditer(text):
            g = m.groups()
            if not re.match(r"\d{1,2}/\d{1,2}/\d{2,4}$", g[2]):
                continue  # wrapped note line, not a data row
            rows.append(
                {
                    "flex": int(g[0]),
                    "identifier": g[1],
                    "date": g[2],
                    "gmt": g[3],
                    "fuel": g[4],
                    "values": [num(x) for x in g[5:14]],
                    "test_end": g[14],
                    "pdf_page": pno,
                }
            )
    return rows


def matrix_tables(pages: list[str]) -> dict[int, dict[str, Any]]:
    """Tables I-VIII (PDF pp.16-21): per-test fiber flag and pressure (atm) where stated."""
    out: dict[int, dict[str, Any]] = {}
    table_no_fiber = {"I", "II", "VIII"}  # captions state 'not supported by a fiber' for the whole table
    current = None
    for pno in range(16, 22):
        for line in pages[pno - 1].splitlines():
            t = re.match(r"TABLE ([IVX]+)\.", line.strip())
            if t:
                current = t.group(1)
            m = MATRIX_RE.match(line.strip())
            if not m or current is None:
                continue
            rest = m.group(3).split()
            fiber = None
            if "Yes" in rest or "No" in rest:
                fiber = "Yes" if "Yes" in rest else "No"
                idx = rest.index(fiber)
                pressure = num(rest[idx + 1]) if idx + 1 < len(rest) else None
            else:
                fiber = "No (table note)" if current in table_no_fiber else None
                nums = [num(x) for x in rest if num(x) is not None]
                pressure = nums[1] if len(nums) >= 2 else None  # D0, P, ...
            out[int(m.group(1))] = {
                "table": current,
                "pdf_page": pno,
                "fiber": fiber,
                "pressure_atm": pressure,
            }
    return out


def captions(pages: list[str]) -> dict[int, dict[str, Any]]:
    text = "".join(f"\n=====PAGE {i}=====\n{p}" for i, p in enumerate(pages, start=1))
    out: dict[int, dict[str, Any]] = {}
    for m in CAPTION_RE.finditer(text):
        pno = text.count("=====PAGE", 0, m.start())
        out.setdefault(
            int(m.group(2)),
            {"figure": int(m.group(1)), "pdf_page": pno, "caption": " ".join(m.group(3).split())},
        )
    return out


def support_mode(caption: str | None) -> tuple[str, str]:
    if caption is None:
        return "unknown", "no caption"
    head = caption[:200].lower()
    if head.startswith("free-floating") or head.startswith("free floating"):
        return "free_floating", "caption: free-floating"
    if head.startswith("fiber-supported") or head.startswith("fiber supported"):
        if re.match(r"fiber.supported \w+ droplet translating", head):
            return "fiber_translated", "caption: fiber-supported ... translating"
        return "fiber_translation_not_stated", "caption: fiber-supported; translation not stated"
    return "unknown", "caption does not state support"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--pypdf-path", default=None)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    data = args.pdf.read_bytes()
    if hashlib.sha256(data).hexdigest() != PDF_SHA256:
        raise SystemExit("report PDF SHA-256 does not match the recorded hash; refusing to build")
    pages = extract_pages(args.pdf, args.pypdf_path)
    t9 = table_ix(pages)
    mats = matrix_tables(pages)
    caps = captions(pages)

    raw = (args.root / "data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv").read_bytes()
    psi = list(csv.reader(io.StringIO(raw.decode("cp1252"))))[1:]
    pool = list(t9)
    out_rows = []
    for r in psi:
        vals = [num(x) for x in r[5:14]]
        hit = next(
            (
                t
                for t in pool
                if t["identifier"] == r[1]
                and t["fuel"] == r[4]
                and t["test_end"] == r[14]
                and all(
                    (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)
                    for a, b in zip(vals, t["values"], strict=True)
                )
            ),
            None,
        )
        if hit is None:
            raise SystemExit(f"PSI row {r[0]} has no exact Table IX match; refusing to guess")
        pool.remove(hit)
        n = int(hit["flex"])
        cap = caps.get(n)
        mode, mode_basis = support_mode(cap["caption"] if cap else None)
        mat = mats.get(n, {})
        mfib = mat.get("fiber")
        if (mfib == "Yes" and mode == "free_floating") or (
            mfib in ("No", "No (table note)") and mode.startswith("fiber")
        ):
            mode_basis = f"{mode_basis}; matrix Table {mat.get('table')} says Fiber={mfib}"
            mode = "conflicting_sources"
        pconf = ""
        p_atm, p_psi = mat.get("pressure_atm"), num(r[5])
        if isinstance(p_atm, float) and p_psi is not None and abs(p_psi / 760 - p_atm) > 0.03:
            pconf = f"Table IX/PSI {r[5]} mmHg vs matrix Table {mat.get('table')} {p_atm} atm"
        ctext = cap["caption"] if cap else ""
        dext_note = "caption_mentions_extrapolation" if re.search(r"extrapolat", ctext, re.I) else ""
        contam = (
            "probable_fuel_contamination (caption)"
            if n == 88
            else "possible_fuel_contamination (caption)"
            if n == 109
            else "sparklers_noted (sec 5.2 item 3: probably contaminant-influenced)"
            if n in (37, 90)
            else ""
        )
        out_rows.append(
            {
                "psi_row": int(r[0]),
                "flex_test_number": n,
                "record_key": f"PSI69-r{int(r[0]):03d}|FLEX-{n:03d}|{r[1]}|{r[2]}|{r[3] or 'no-GMT'}",
                "identifier": r[1],
                "test_date_psi": r[2],
                "test_gmt_psi": r[3],
                "table_ix_pdf_page": hit["pdf_page"],
                "table_ix_printed_page": int(hit["pdf_page"]) - PRINTED_PAGE_OFFSET,
                "match_method": "exact match on identifier, fuel, test end and 9 numeric Table IX fields",
                "support_mode": mode,
                "support_basis": mode_basis,
                "caption_figure": cap["figure"] if cap else "",
                "caption_pdf_page": cap["pdf_page"] if cap else "",
                "matrix_table": mat.get("table", ""),
                "matrix_table_fiber": mat.get("fiber")
                or ("not_in_matrix_tables" if n > 166 else "not_stated"),
                "matrix_table_pressure_atm": "" if mat.get("pressure_atm") is None else mat["pressure_atm"],
                "pressure_source_conflict": pconf,
                "shutter_1_30s_period": n <= 9,
                "coated_needle_period": True,
                "documented_contamination_or_feature": contam,
                "dext_caption_note": dext_note,
                "verification_status": "pypdf text extraction; not visually verified",
            }
        )
    out_dir = args.root / "data" / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"flex_enrichment_v{ENRICHMENT_VERSION}.csv").open(
        "w", encoding="utf-8", newline=""
    ) as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    cap_out = {
        "source": {
            "report": REPORT,
            "pdf_sha256": PDF_SHA256,
            "url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf",
            "extraction": "pypdf text extraction of Appendix B figure captions",
        },
        "unmatched_table_ix_rows": [
            {"flex": t["flex"], "identifier": t["identifier"], "date": t["date"]} for t in pool
        ],
        "flex_numbers_without_caption": sorted(set(range(1, 281)) - set(caps)),
        "captions": {f"FLEX-{k:03d}": v for k, v in sorted(caps.items())},
    }
    (out_dir / f"flex_enrichment_v{ENRICHMENT_VERSION}_captions.json").write_text(
        json.dumps(cap_out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"enrichment rows: {len(out_rows)}; unmatched Table IX rows: {[t['flex'] for t in pool]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
