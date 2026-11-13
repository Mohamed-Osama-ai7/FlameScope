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

The NASA Global Organizing Team stated that teams must use at least one NASA data source listed in the challenge's own **Resources** tab to be eligible for Global Awards. The GO Team answer in nasa/spaceapps discussion #1849 (Nov 6, 2026) says challenge resources become available on **November 12** under the challenge page's Resources tab. As of 2026-11-13 that exact resource list has **not** been imported or verified here (the challenge page failed TLS verification from the audit machine — open it in a normal browser). Add the official resource(s) to `data/metadata/source_registry.csv` as soon as they are available, record the exact resource title/URL/version/license, and verify its actual use in the product. Candidate PSI investigations listed below are supplemental candidates until checked against that official Resources tab.

## Stack (initial implementation)

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI + Pydantic
- Structured storage: PostgreSQL + SQLAlchemy
- Retrieval (later MVP increment): Qdrant + BM25 + BGE-M3 + a reranker, only after a source corpus and evaluation set exist
- Scientific computing: NumPy 2.x is a core backend dependency; Pandas 2.x is optional for data tooling; SciPy, Statsmodels, and scikit-learn are not installed by the backend package
- Visualization: Plotly Cartesian engine (`plotly.js-cartesian-dist-min` 2.35.3) with `react-plotly.js` 2.6.0
- Frontend tests: Vitest 3.0.5 and Playwright 1.65.0 (with axe accessibility checks)
- Backend tests: Pytest

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

The frontend API client uses `http://127.0.0.1:8000` by default. Set `VITE_API_BASE_URL` to the backend origin when it runs elsewhere.

### 3. Audit downloaded files without modifying them

From the repository root:

```bash
python backend/scripts/audit_local_data.py --root data/raw --output data/metadata/local_file_inventory.csv
```

The script records file paths, sizes, extensions, and SHA-256 hashes. It does not infer scientific meaning or change original files.

### 4. Checks

```bash
python -m pytest -q backend/tests
ruff check backend/app backend/scripts backend/tests && mypy backend/app backend/scripts
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend run typecheck:tests
npm --prefix frontend run test:e2e
```

Playwright runs Chromium against the production Vite preview. The browser project uses system Chrome (`channel: chrome`), which must be installed for the E2E command.

Architecture audit, target design and backlog: [`docs/08_architecture_audit.md`](docs/08_architecture_audit.md).

## Repository map

- `docs/` — problem contract, MVP scope, scientific gates, sprint roles, AI disclosure
- `data/raw/` — untouched source files; never overwrite originals
- `data/metadata/source_registry.csv` — sources, official challenge-resource flag, license and verification status
- `data/metadata/local_file_inventory.csv` — generated local inventory
- `database/schema.sql` — initial relational model with provenance links
- `backend/` — API and deterministic file-audit utility
- `frontend/` — React + TypeScript scientific exploration lab, searchable FLEX records, source/regime/method API explorer, Plotly charts, typed API client, Vitest and Playwright suites

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
