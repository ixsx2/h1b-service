# Deploy checklist (Phase 2)

Everything below can be done in parallel. Items marked **you** need your accounts/secrets; the rest is already in the repo.

## Already wired (no secrets needed)

| Piece | Location |
|-------|----------|
| Heroku `app.json` (Postgres addon, env template) | `app.json` |
| Release-phase schema init | `Procfile` → `release:` |
| Buildpack fallback (`bin/post_compile`) | builds `data/h1b_data.db` from fixtures |
| GitHub Actions CI | `.github/workflows/ci.yml` |
| Deploy workflow (skips until secrets set) | `.github/workflows/deploy.yml` |
| Quarterly ETL cron | `.github/workflows/etl.yml` |
| ETL manifest + downloader | `etl/manifest.json`, `python -m etl.download` |
| Post-deploy smoke script | `scripts/smoke.py` |
| Testmail e2e (skips until secrets set) | `tests/test_testmail_e2e.py` |
| SimpleAnalytics toggle | `SIMPLE_ANALYTICS=1` env var |

## **You** — one-time setup

### 1. GitHub repo

```bash
git remote add origin https://github.com/ixsx2/h1b-service.git
git push -u origin master
```

### 2. GitHub Actions secrets

| Secret | Used by |
|--------|---------|
| `HEROKU_API_KEY` | `deploy.yml` |
| `HEROKU_APP_NAME` | `deploy.yml` |
| `HEROKU_EMAIL` | `deploy.yml` (Heroku account email) |
| `TESTMAIL_API_KEY` | `ci.yml` Testmail job |
| `TESTMAIL_NAMESPACE` | `ci.yml` Testmail job |
| `HONEYBADGER_ETL_CHECKIN_URL` | `etl.yml` (optional) |

### 3. Heroku app

```bash
heroku create YOUR_APP_NAME
heroku addons:create heroku-postgresql:essential-0
heroku config:set OTP_SECRET=$(openssl rand -hex 32)
heroku config:set EMAIL_FROM=otp@YOURDOMAIN.dev
heroku config:set RESEND_API_KEY=re_...
heroku config:set DEMO_EMPLOYER=DATADOG
heroku config:set SIMPLE_ANALYTICS=1   # after domain is live
```

`DATABASE_URL` is set automatically by the Postgres addon.

### 4. Resend + DNS

1. Create Resend account, add your `.dev` domain.
2. Add DKIM (and SPF if prompted) records at Name.com.
3. Set `EMAIL_FROM` to a verified sender (e.g. `otp@yourname.dev`).

### 5. Custom domain

```bash
heroku domains:add yourname.dev
heroku domains:add www.yourname.dev
```

Point Name.com DNS to the Heroku DNS targets shown by `heroku domains`.

### 6. Real ETL data (before calling production “live”)

1. Download FY2025/FY2026 DOL xlsx + USCIS CSV (see `tests/fixtures/real/README.md`).
2. Paste USCIS CSV URL into `etl/manifest.json`.
3. Run locally:

```bash
python -m etl.download --output data/sources
python scripts/build_data.py --source manifest
pytest tests/test_real_etl.py -v
```

4. Re-run deploy (CI bundles the built `h1b_data.db`).

## Verify live funnel

```bash
# Partial (no real email)
python scripts/smoke.py --base-url https://YOUR_APP.herokuapp.com

# Full (after Resend is live)
python scripts/smoke.py \
  --base-url https://yourname.dev \
  --email you@yourmail.com \
  --otp-code 123456
```

Or trigger **Deploy** workflow manually in GitHub Actions after secrets are set.

## Monitoring (Phase 4 — optional env vars)

| Service | Env var | When |
|---------|---------|------|
| Sentry | `SENTRY_DSN` | Add `sentry-sdk` + init when ready |
| Honeybadger | `HONEYBADGER_ETL_CHECKIN_URL` | ETL cron watchdog |
| SimpleAnalytics | `SIMPLE_ANALYTICS=1` | Landing page script |

## What deploy does

```mermaid
flowchart LR
  A[push main] --> B[build h1b_data.db]
  B --> C[git add -f data/h1b_data.db]
  C --> D[heroku deploy]
  D --> E[release: Postgres schema]
  E --> F[smoke healthz + demo]
```

Quarterly `etl.yml` rebuilds the database from manifest URLs and uploads an artifact; update deploy to consume that artifact when you want production data refreshes without a code push.
