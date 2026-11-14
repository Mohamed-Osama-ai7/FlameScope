"""Load verified NASA source files into the FlameScope scientific database.

Usage (from backend/, after `alembic upgrade head`):
    python scripts/load_database.py                      # every PSI source in the registry
    python scripts/load_database.py --source PSI-69      # one source
    python scripts/load_database.py --json               # machine-readable report

Exit codes: 0 = every source that has an extractor loaded; 1 = a load was refused (nothing written);
2 = configuration problem (no database URL, schema not at head).
Reads data/raw and data/metadata only; never writes to them. Safe to re-run (idempotent).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.data_platform.db import make_engine, session_factory
from app.data_platform.extract_flex import ExtractionRefused
from app.data_platform.loader import SchemaNotReady, load_all
from app.data_platform.settings import DATABASE_URL_ENV, database_url, project_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", action="append", dest="sources", help="registry source_id (repeatable)")
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: auto)")
    parser.add_argument("--database-url", default=None, help=f"default: ${DATABASE_URL_ENV}")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    url = args.database_url or database_url()
    if not url:
        print(f"ERROR: set {DATABASE_URL_ENV} or pass --database-url", file=sys.stderr)
        return 2
    root = (args.root or project_root()).resolve()
    engine = make_engine(url)
    try:
        with session_factory(engine)() as session:
            report = load_all(session, root, args.sources)
    except SchemaNotReady as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ExtractionRefused as exc:
        print(f"REFUSED (nothing written): {exc}", file=sys.stderr)
        for c in exc.checks:
            if c.blocking:
                print(f"  - {c.check_name}: {c.affected_count} affected; {c.details}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps([asdict(r) for r in report.results], indent=2))
    else:
        for r in report.results:
            if r.loaded:
                print(
                    f"LOADED  {r.source_id}: {r.runs} runs, {r.measurements} measurements "
                    f"(removed stale: {r.deleted_runs} runs, {r.deleted_measurements} measurements); "
                    f"extraction_run {r.extraction_run_id}"
                )
                for w in r.warnings:
                    print(f"        flagged  {w}")
            else:
                print(f"SKIPPED {r.source_id}: {r.reason}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
