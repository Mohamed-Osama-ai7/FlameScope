Verbatim API responses used by `tests/unit/rag-client.test.ts`.

Captured 2026-11-14 from the merged backend (branch `feat/rag-scientific-copilot`, which contains the Data
Platform) running locally with a SQLite platform database loaded by `backend/scripts/load_database.py`
(PSI-69 only; PSI-25 skipped, PSI-98 refused). Recapture with the same requests if the API contract changes:
`GET /api/v1/sources`, `GET /api/v1/rag/sources`, `POST /api/v1/copilot/ask` (questions in the test names),
`POST /api/v1/rag/search {"query":"FLEX-114 ambient pressure","top_k":3}`, `GET /api/v1/rag/chunks/PSI-25:row:001` (403).
