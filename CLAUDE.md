# CLAUDE.md — working rules for this repository

FinSight is an AI-powered financial intelligence platform for **Indian listed companies
(NSE/BSE)**: FastAPI + PostgreSQL backend, React + Vite frontend. Only ₹0 data sources may be
integrated (demo default, Tej keyless EOD, optional yfinance); SEC EDGAR is an optional US
market. **Read `SYSTEM_FLOW.md` first** — it is the source of truth for what is actually
implemented.

## Commands

Backend (run in `backend/`, venv at `backend/.venv`):

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows; use .venv/bin on Unix
.venv/Scripts/python -m pytest            # SQLite by default; set TEST_DATABASE_URL for Postgres
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
.venv/Scripts/mypy
.venv/Scripts/alembic upgrade head        # uses FINSIGHT_DATABASE_URL
.venv/Scripts/alembic revision --autogenerate -m "describe change"
```

Frontend (run in `frontend/`):

```bash
npm ci
npm run dev      # http://localhost:5173, proxies /api → http://localhost:8000
npm test         # Vitest + React Testing Library
npm run lint
npm run build    # tsc --noEmit + vite build
```

## Rules

1. **Keep `SYSTEM_FLOW.md` in sync** with every change to endpoints, schemas, tables,
   calculations, providers, or security. Update the feature matrix status honestly.
2. **Financial integrity**
   - Financial calculations live in `backend/app/domain/`: pure, deterministic, `Decimal`-only
     functions with unit tests. No I/O imports there (a test enforces this).
   - Never invent market data, statements, or citations. Missing data stays missing.
   - Every figure carries source, currency, unit/scale, and period. Distinguish *reported*,
     *calculated*, *assumption*, *forecast*, and *AI explanation*.
   - Validate DCF inputs (e.g. WACC > terminal growth) and reject invalid assumptions explicitly.
3. **Secrets** live only in backend env (`FINSIGHT_*`, read in `app/core/config.py`). Never in
   frontend code, never committed. `.env` is git-ignored; update `.env.example` with placeholders.
4. **API conventions:** routes under `/api/v1`; Pydantic request/response models; errors raised
   as `AppError(code, message, status_code)` so they use the standard envelope. Layering:
   `api` → `services` → `models` / `providers` / `domain`. Every user-owned query filters by
   `owner_id` and returns 404 for other users' resources; add a cross-user test for each new
   owned resource. Tests never hit the network: use `tests/fakes.py` / `httpx.MockTransport`.
5. **Database:** every schema change ships with an Alembic migration; the drift test must pass.
   Import new model modules in `app/models/__init__.py`.
6. **Frontend:** call the API only through `src/lib/api.ts` (`apiFetch`) inside TanStack Query
   hooks colocated in `src/features/<feature>/`. Mirror backend schemas as TS interfaces.
7. **Git:** develop on `dev/claude`; `main` is stable. Conventional Commits. Inspect the diff
   before staging. No force-push, no history rewriting, no merging to `main` and no pushing
   without explicit authorization. Run tests/builds before committing and report results
   accurately.

## Phase roadmap

0 inspection & docs (✅) · 1 foundation (✅) · 2 financial domain engine (✅) · 3 APIs, auth, persistence (✅) ·
India-first migration, free providers (✅) · 4 frontend workspace (✅) · 5 annual reports + Claude with citations (✅) · 6 reports & export (✅) ·
7 verification & security audit (✅).
