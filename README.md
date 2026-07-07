# H-1B Sponsorship Signal API

Public pilot API answering **"would this company sponsor an H-1B?"** from DOL LCA
disclosure files and the USCIS H-1B Employer Data Hub.

**Repo:** https://github.com/ixsx2/h1b-service

## Status (2026-07-07)

| Milestone | State |
|-----------|--------|
| Phase 1 — ETL, signal logic, local API, pytest (CP0–CP5) | Done |
| Phase 2 — landing, OTP flow, mock-email e2e | Done |
| Phase 2b — deploy prep (workflows, Heroku manifest, ETL cron) | Done |
| Phase 3 — live deploy | **In progress** — CI/deploy green; awaiting your Heroku + Resend + domain |
| Phase 4 — monitoring + publish | Not started |

**CI:** 31 passed, 2 skipped · **ruff** clean

Production slug currently ships **synthetic fixture data** (DATADOG demo). Real
DOL/USCIS build required before calling the service "live."

## What's built

- Six-route FastAPI API with passwordless OTP → API key auth
- Sponsorship Signal tiers + USCIS denial rate + employer lookup (FTS5)
- ETL pipeline with quarterly GitHub Actions cron
- Landing page with demo box + inline signup
- Deploy workflow (bundles `h1b_data.db`, pushes to Heroku when secrets set)

## Next steps

### You (unblocks public URL)

1. Pick a `.dev` domain name (Name.com / Student Pack)
2. `heroku login` → `python scripts/heroku_bootstrap.py` → create app + Postgres
3. Add GitHub secrets: `HEROKU_API_KEY`, `HEROKU_APP_NAME`, `HEROKU_EMAIL`
4. Run **Deploy** workflow on GitHub Actions
5. Resend + DKIM → set `RESEND_API_KEY`, `EMAIL_FROM` on Heroku
6. Point DNS at Heroku; run full smoke (see [docs/deploy.md](docs/deploy.md))

### Before "live" label

7. Real FY2025/FY2026 DOL + USCIS files → `tests/fixtures/real/` → `pytest tests/test_real_etl.py`
   **Manual step required:** `www.dol.gov` returns HTTP 403 to all non-interactive
   clients (Akamai bot protection), so `etl.download` cannot fetch DOL xlsx files.
   Download them in a browser from the [OFLC performance page](https://www.dol.gov/agencies/eta/foreign-labor/performance),
   drop into `data/sources/`, then `python scripts/build_data.py --source manifest`.
   USCIS host is not blocked — grab the CSV from the [Data Hub files page](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub/h-1b-employer-data-hub-files).
8. Optional: Testmail secrets for CI OTP e2e

### After live

9. SimpleAnalytics, Sentry, Honeybadger; publish and measure engagement (SQL below)

Full checklist: [docs/deploy.md](docs/deploy.md) · Phase detail: [PLAN.md](PLAN.md)

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
python scripts/build_data.py --source fixtures

# Real files — download then build
python -m etl.download --output data/sources   # URLs in etl/manifest.json
python scripts/build_data.py --source manifest
```

- **Quarterly cron:** `.github/workflows/etl.yml` (Jan/Apr/Jul/Oct 15)
- **Deploy:** `.github/workflows/deploy.yml` when Heroku secrets are set

## API (frozen surface)

| Route | Auth | Purpose |
|-------|------|---------|
| `GET /` | open | Landing + demo + OTP signup |
| `GET /healthz` | open | Uptime + `data_db` present |
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

- [PLAN.md](PLAN.md) — decisions, work log, next steps
- [CONTEXT.md](CONTEXT.md) — domain glossary
- [docs/deploy.md](docs/deploy.md) — Heroku, secrets, DNS, smoke
- [docs/future-considerations.md](docs/future-considerations.md) — Sponsorly positioning
- [docs/adr/](docs/adr/) — architecture decisions
