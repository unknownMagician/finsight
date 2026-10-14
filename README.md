# FinSight — AI-Powered Financial Intelligence Platform

FinSight is a modular platform for company research: financial statement analysis, ratio
calculations, DCF and comparable-company valuation, scenario forecasting, annual-report
intelligence, and an AI research assistant that cites its sources.

> **Status: Phase 1 (foundation).** The project skeleton, configuration, database migrations,
> health checks, tests, Docker, and CI are in place. Financial features are not built yet — see
> the feature matrix in [`SYSTEM_FLOW.md`](SYSTEM_FLOW.md).

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router, TanStack Query, Recharts |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 17 |
| AI | Claude API via a backend-only adapter (Phase 5) |
| Testing | pytest, Vitest, React Testing Library, Playwright (Phase 4) |
| Infra | Docker Compose, GitHub Actions |

## Quick start (Docker)

```bash
cp .env.example .env        # set POSTGRES_PASSWORD (and later API keys)
docker compose up --build
```

- App: http://localhost:8080
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health/ready

## Local development

**Backend**

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # macOS/Linux: .venv/bin/pip
# Point at a Postgres (e.g. `docker compose up db`) or use SQLite for a quick try:
export FINSIGHT_DATABASE_URL=sqlite:///./dev.db
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm ci
npm run dev                                  # http://localhost:5173 (proxies /api → :8000)
```

## Tests & checks

```bash
# backend/
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check . && .venv/Scripts/mypy

# frontend/
npm test && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs all of the above, the backend suite against PostgreSQL, and
builds both Docker images.

## Documentation

- [`SYSTEM_FLOW.md`](SYSTEM_FLOW.md) — architecture, data flows, API, database, security, and
  feature status (source of truth).
- [`CLAUDE.md`](CLAUDE.md) — conventions and rules for contributors and AI agents.

## Data disclaimer

FinSight never fabricates market data, financial statements, or citations. Figures are labeled as
reported, calculated, assumed, forecast, or AI-generated explanation. Nothing here is investment
advice.
