# FinSight — AI-Powered Financial Intelligence Platform

FinSight is a modular platform for researching **Indian listed companies (NSE and BSE)**:
financial statement analysis, ratio calculations, market multiples, DCF and comparable-company
valuation, scenario forecasting, and (planned) an AI research assistant that cites its sources.

> **Status: India-first, free data only.** Company search with NSE/BSE listing selection,
> end-of-day prices and charts, corporate actions, annual and quarterly statements
> (consolidated/standalone), ratios and a valuation snapshot, in the API and a web UI.
> It runs offline by default on clearly labelled **demo** data. Real NSE/BSE end-of-day data
> comes from the free, keyless Tej API. US companies via SEC EDGAR remain available as an
> optional market. See the feature matrix in [`SYSTEM_FLOW.md`](SYSTEM_FLOW.md).

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router, TanStack Query, Recharts |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 17 |
| AI | Claude API via a backend-only adapter (Phase 5) |
| Market data | Tej API (free, keyless EOD), optional yfinance, built-in demo provider; SEC EDGAR (optional US) |
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

### Data providers (all ₹0, no keys needed)

| Setting | Values | Default |
|---|---|---|
| `FINSIGHT_MARKET_DATA_PROVIDER` | `demo` (synthetic, offline) · `tej` (free keyless NSE/BSE end-of-day data) | `demo` |
| `FINSIGHT_FUNDAMENTALS_PROVIDER` | `demo` · `yfinance` (optional, unofficial, **personal use only**) · `none` | `demo` |

With the defaults, sign up in the UI and search “demo”. To use real NSE/BSE data:

```bash
export FINSIGHT_MARKET_DATA_PROVIDER=tej
.venv/Scripts/python -m app.cli sync-instruments      # NSE + BSE directory from the latest snapshot
# optional statements via Yahoo Finance (personal use only):
.venv/Scripts/pip install -e ".[yfinance]"
export FINSIGHT_FUNDAMENTALS_PROVIDER=yfinance
.venv/Scripts/python -m app.cli ingest RELIANCE TCS
```

Prices are end-of-day (not real-time) and unadjusted. Shareholding, announcements and intraday
prices have no free source and are reported as unavailable. Read the licensing notes in
`SYSTEM_FLOW.md` §16 before any commercial use.

**Optional US market (SEC EDGAR):** set `FINSIGHT_SEC_USER_AGENT` (e.g. `FinSight
you@example.com`), then `python -m app.cli sync-companies` and
`python -m app.cli ingest --market US AAPL`, or call the API with `?market=US`.

Try the API at http://localhost:8000/docs: register, log in, and click *Authorize* with the token.

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
