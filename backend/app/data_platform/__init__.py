"""FlameScope scientific data platform (workstream: Data Engineering / Backend / Scientific Data).

Turns acquired NASA PSI files into a provenance-complete relational store:

    source_registry.csv + artifact_manifest.csv      (what was acquired, from where, licence, SHA-256)
            |  verify bytes (SHA-256 + size) - refuse on mismatch, refuse QUARANTINED sources
            v
    extractors (pure functions, no DB)               (one record per source cell, original text kept)
            |  data-quality checks: structural errors block the load, scientific anomalies become flags
            v
    PostgreSQL via SQLAlchemy + Alembic              (investigations, artifacts, runs, measurements, ...)
            |
            v
    FastAPI /api/v1 (api.py)                         (every measurement resolves to artifact + row + column)

Design rules (docs/14_scientific_data_platform.md):
* Raw files are read-only inputs. Nothing here writes to data/raw.
* Identifiers are deterministic (UUIDv5 of content + location), so a reload yields identical rows.
* Parsing reuses app.analysis.flex_run_level so the database and the analysis read the file identically.
"""
