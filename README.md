# H-1B Sponsorship Signal API

Public pilot API answering **"would this company sponsor an H-1B?"** from DOL LCA
disclosure files and the USCIS H-1B Employer Data Hub.

## Status

| Milestone | State |
|-----------|--------|
| Phase 1 — ETL, signal logic, local API, pytest | Done |
| Phase 2 — landing, OTP flow, mock-email e2e | Done |
| Phase 2b — deploy prep (workflows, Heroku manifest, ETL cron) | Done |
| Phase 3 — live deploy (Heroku, Postgres, domain, Resend) | **Blocked on you** |

Tests: **31 passed, 2 skipped** (`test_real_etl`, `test_testmail_e2e`).

Deploy checklist: **[docs/deploy.md](docs/deploy.md)**

## Quick start (local)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

python -m etl.build --fixtures tests/fixtures
uvicorn app.main:app --reload
```

```bash
pytest
ruff check .
```

## ETL

```bash
# Synthetic fixtures (CI / dev / initial Heroku slug)
python -m etl.build --fixtures tests/fixtures
# or
python scripts/build_data.py --source fixtures

# Real files — download then build
python -m etl.download --output data/sources   # URLs in etl/manifest.json
python scripts/build_data.py --source manifest

# Manual paths
python -m etl.build \
  --dol tests/fixtures/real/LCA_Disclosure_Data_FY2025_Q4.xlsx \
  --uscis tests/fixtures/real/employer_h1b_data_hub_fy2025.csv
```

- **Quarterly cron:** `.github/workflows/etl.yml` (Jan/Apr/Jul/Oct 15) uploads `h1b_data.db` artifact.
- **Deploy:** `.github/workflows/deploy.yml` bundles DB into slug and pushes to Heroku when secrets are set.

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

## Deploy (when ready)

1. Set GitHub secrets: `HEROKU_API_KEY`, `HEROKU_APP_NAME`, `HEROKU_EMAIL`
2. Heroku config: `OTP_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`, `DATABASE_URL` (from Postgres addon)
3. Push to `main` / run **Deploy** workflow
4. Smoke: `python scripts/smoke.py --base-url https://YOUR_APP.herokuapp.com`

Full steps: [docs/deploy.md](docs/deploy.md)

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
- [docs/deploy.md](docs/deploy.md) — Heroku, secrets, DNS, smoke
- [docs/adr/](docs/adr/) — architecture decisions
