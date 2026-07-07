# H-1B Sponsorship Signal API

Public pilot API answering **"would this company sponsor an H-1B?"** from DOL LCA
disclosure files and the USCIS H-1B Employer Data Hub.

## Status

Phase 1 in progress: ETL, signal logic, local API, and test suite.

## Quick start (local)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

# Build aggregates from fixtures (or real DOL/USCIS files — see below)
python -m etl.build --fixtures tests/fixtures

# Run API
uvicorn app.main:app --reload

# Tests
pytest
ruff check .
```

## ETL

```bash
# Synthetic fixtures (CI / dev)
python -m etl.build --fixtures tests/fixtures

# Real files (download from DOL + USCIS first)
python -m etl.build \
  --dol tests/fixtures/real/LCA_Disclosure_Data_FY2025_Q4.xlsx \
  --dol tests/fixtures/real/LCA_Disclosure_Data_FY2026_Q1.xlsx \
  --uscis tests/fixtures/real/employer_h1b_data_hub_fy2025.csv
```

Quarterly GitHub Actions cron rebuilds `h1b_data.db` and ships it with each release.

## API (frozen surface)

| Route | Auth | Purpose |
|-------|------|---------|
| `GET /` | open | Landing + demo + OTP signup |
| `GET /healthz` | open | Uptime |
| `GET /v1/demo` | open, 30/day/IP | Canned example |
| `POST /auth/code`, `/auth/verify` | rate-limited | Passwordless OTP → API key |
| `GET /v1/signal?company=X` | key, 500/day | Signal tier + trend + denial rate |
| `GET /v1/employer/{name}` | key, 500/day | Full Employer-Year Aggregates |

Errors: `{"error": "...", "hint": "..."}`.

## Engagement metrics (Postgres)

Once deployed, run against the `request_log` and `api_keys` tables:

```sql
-- Signups per week
SELECT date_trunc('week', created_at) AS week, count(*) AS signups
FROM users GROUP BY 1 ORDER BY 1 DESC;

-- Activation rate (signup → ≥1 real /v1/* call)
SELECT
  count(DISTINCT u.id) FILTER (WHERE rl.key_id IS NOT NULL)::float
  / nullif(count(DISTINCT u.id), 0) AS activation_rate
FROM users u
LEFT JOIN api_keys ak ON ak.user_id = u.id
LEFT JOIN request_log rl ON rl.key_id = ak.id AND rl.endpoint LIKE '/v1/%';

-- Weekly-active keys
SELECT count(DISTINCT key_id) FROM request_log
WHERE timestamp >= now() - interval '7 days' AND endpoint LIKE '/v1/%';

-- Top queried employers (last 30 days)
SELECT query, count(*) AS lookups FROM request_log
WHERE endpoint = '/v1/signal' AND timestamp >= now() - interval '30 days'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
```

## Docs

- [PLAN.md](PLAN.md) — settled decisions and phases
- [CONTEXT.md](CONTEXT.md) — domain glossary
- [docs/adr/](docs/adr/) — architecture decisions
