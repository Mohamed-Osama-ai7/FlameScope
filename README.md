# UnderFitted | FlameScope

**NASA challenge:** *Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data*  
**Team:** UnderFitted  
**Product concept:** FlameScope — an evidence-driven scientific research intelligence system for microgravity-combustion research.

> Independent hackathon project. Not developed, approved, endorsed, or certified by NASA. Research-use only; not an operational spacecraft fire-safety, alarm, or control system.

## The problem we are solving

NASA's microgravity-combustion results are distributed across investigations, reports, measurements, and imagery. Researchers need to find relevant evidence, understand whether two experiments are comparable, inspect the original source, and reason from the measurements without losing experimental context.

FlameScope is therefore **not a generic chatbot or a collection of AI features**. Its primary product is a traceable evidence-to-insight workflow:

`Question → Relevant investigations → Source-backed evidence → Validity/comparability checks → Quantitative analysis → Uncertainty & limitations → Research insight`

## Important launch gate

The NASA Global Organizing Team stated that teams must use at least one NASA data source listed in the challenge's own **Resources** tab to be eligible for Global Awards. The GO Team answer in nasa/spaceapps discussion #1849 (Nov 6, 2026) says challenge resources become available on **November 12** under the challenge page's Resources tab. **Status 2026-11-13: recorded and in use.** The Resources tab names *PSI Data Repository: Combustion Science* (https://psi.nasa.gov/physci/repo/search?q=combustion) as the source of the data the app is to be based on. It is registered as `CHALLENGE-RESOURCE-01` in `data/metadata/source_registry.csv`. PSI-69 (FLEX), PSI-25 (BASS-II) and PSI-98 have PSI `researchArea = Combustion Science`. PSI-69 is verified by SHA-256 and loaded into the scientific database (`GET /api/v1/data-platform/status` → `official_challenge_resource_loaded: true`). Evidence and its limits: [`docs/14_scientific_data_platform.md`](docs/14_scientific_data_platform.md) §2. The team lead should re-check the live Resources tab before submission; eligibility is decided by the Global Organizing Team.

## Stack (initial implementation)

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI + Pydantic
- Structured storage: PostgreSQL + SQLAlchemy
- Retrieval (later MVP increment): Qdrant + BM25 + BGE-M3 + a reranker, only after a source corpus and evaluation set exist
- Scientific computing: NumPy, Pandas, SciPy, Statsmodels, scikit-learn
- Visualization: Plotly (add after the data contract stabilizes)
- Testing: Pytest

Keep a modular monolith. Do not add agents, microservices, model fine-tuning, or advanced CFD until a measurable need is demonstrated.

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Audit downloaded files without modifying them

From the repository root:

```bash
python backend/scripts/audit_local_data.py --root data/raw --output data/metadata/local_file_inventory.csv
```

The script records file paths, sizes, extensions, and SHA-256 hashes. It does not infer scientific meaning or change original files.

### 4. Scientific database (PostgreSQL)

```bash
python backend/scripts/fetch_psi_table.py PSI-69 PSI-25 PSI-98 --root .   # raw NASA files (gitignored)
docker compose up -d --build        # PostgreSQL + API on http://127.0.0.1:8000 (migrations run on start)
docker compose run --rm loader      # verify SHA-256, validate, load PSI-69 (idempotent)
```

Every stored measurement links to its NASA artifact (SHA-256), row, column, verbatim source text and
quality flags: `GET /api/v1/measurements/{id}/provenance`. Details: [`docs/14_scientific_data_platform.md`](docs/14_scientific_data_platform.md).

### 5. Checks

```bash
cd backend && pytest -q && ruff check app scripts tests && mypy app scripts
cd frontend && npm run build
```

Architecture audit, target design and backlog: [`docs/08_architecture_audit.md`](docs/08_architecture_audit.md).

## Repository map

- `docs/` — problem contract, MVP scope, scientific gates, sprint roles, AI disclosure
- `data/raw/` — untouched source files; never overwrite originals
- `data/metadata/source_registry.csv` — sources, official challenge-resource flag, license and verification status
- `data/metadata/local_file_inventory.csv` — generated local inventory
- `database/schema.sql` — PostgreSQL schema rendered from the Alembic migrations (generated; do not edit)
- `backend/app/data_platform/` — SQLAlchemy models, Alembic migrations, verified loader, data-quality checks, provenance API
- `docker-compose.yml` — PostgreSQL + API + loader for local runs
- `backend/` — API and deterministic file-audit utility
- `frontend/` — minimal working project shell; no fabricated scientific results

## Scientific integrity rules

1. Never create placeholder measurements that look real.
2. Keep raw files immutable; derived data must retain source artifact, page/table/frame, extraction method, units, and transformation history.
3. Distinguish files, investigations, experimental runs, test records, and measurements.
4. Never compare different combustion regimes on an unqualified common outcome axis.
5. A file hash demonstrates byte-level integrity relative to a recorded file; it does not validate scientific correctness.
6. Every model output must expose evidence, assumptions, units, uncertainty, applicability limits, and abstention behavior.
7. Treat all model choices and target metrics as provisional until benchmarked on the actual corpus.

## Team workflow

Use short-lived branches and pull requests. One owner per module, one integrator, and a review before merging. Do not commit downloaded data unless the source license and repository size make that appropriate. Never commit API keys, private participant information, or unlicensed files.
