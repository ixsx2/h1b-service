# H1B Data Service — Pilot Plan

Status: **Phases 1–2b complete; Phase 3 in progress** (2026-07-07). Public repo
live at https://github.com/ixsx2/h1b-service — CI and Deploy workflows green.
First Heroku push awaits Ishan's secrets (Heroku app, Resend, `.dev` domain).
Real-file ETL test skips until DOL/USCIS files in `tests/fixtures/real/`.
Read [CONTEXT.md](CONTEXT.md) for domain terms and [docs/adr/](docs/adr/) for
recorded decisions before changing anything here.

## Goal

Public-ready pilot API answering "would this company sponsor an H-1B?" from
DOL LCA disclosure files + USCIS H-1B Employer Data Hub. Minimal feature set;
engagement measurement is a first-class requirement. Also serves as a public
data-engineering portfolio artifact.

## Decisions (settled — do not re-litigate without cause)

1. **Audience**: public-ready pilot; just enough features to measure engagement.
2. **Home**: this directory, own git repo (public). ZERO imports from
   Projects/JobApps — copy shared logic (e.g. name-variant suffix stripping),
   never import across the boundary. JobApps stays a separate stack for now
   (explicitly decided: no dogfooding integration yet).
3. **Data scope**: Employer-Year Aggregates only (no raw filings), last 5
   fiscal years, both sources. Key = (Canonical Employer, fiscal year).
   USCIS join (approvals/denials → denial rate) is the differentiator.
4. **Sponsorship Signal tiers** (grade, never a score):
   - ACTIVE: >=20 certified LCAs in latest complete FY
   - ESTABLISHED: >=20 certified across last 3 FYs, <20 latest
   - RARE: >0 certified in last 5 FYs, below the above
   - NONE: zero in 5 FYs
   - Orthogonal fields, never folded into tier: trend (rising|falling|flat,
     null when both years <10) and denial_rate (USCIS initial denials /
     initial decisions, latest FY, null when petitions <10; caution flag when
     >=15% with real volume).
5. **Lookup semantics**: canonicalize query -> exact match; miss -> FTS5 fuzzy
   over canonical + filed names; single confident hit -> answer with
   `matched_as`; multiple -> `candidates` list and NO signal (never auto-pick);
   nothing -> `matched: false` (distinct from tier NONE). `matched: false`
   responses are never cached.
6. **Auth**: passwordless email OTP -> long-lived API key. POST /auth/code
   (6-digit, 10-min expiry, hashed, max 5 attempts, 3 codes/hour per email AND
   per IP) -> POST /auth/verify -> key (hashed server-side, shown once).
   Signup and login are the same flow. No passwords ever.
7. **Email**: Resend free tier + DKIM on the .dev domain.
8. **Hosting**: Heroku via GitHub Student Pack credit ($13/mo x 24 = $0 out of
   pocket). See ADR-0001: aggregates SQLite ships in the slug; user data in
   Heroku Postgres (ephemeral filesystem forbids writable local files).
9. **ETL**: GitHub Actions quarterly cron downloads DOL xlsx + USCIS CSV,
   builds h1b_data.db, ships it with the release. Same script runnable
   locally (`python -m etl.build`). Per-fiscal-year column maps (DOL columns
   drift). First build runs locally to validate maps against real files.
10. **API surface (FROZEN — six routes)**:
    | Route | Auth | Purpose |
    |-------|------|---------|
    | GET / | open | landing: pitch, demo box (card + raw JSON tabs), inline OTP->key flow, curl quickstart |
    | GET /healthz | open | uptime |
    | GET /v1/demo | open, 30/day/IP | canned live example (fixed employer) |
    | POST /auth/code, /auth/verify | open, rate-limited | OTP -> API key |
    | GET /v1/signal?company=X | key | Signal Tier + counts by FY + trend + denial_rate + match semantics |
    | GET /v1/employer/{name} | key | full aggregates: per-FY certified, salary median/range, top titles, USCIS approvals/denials |
    Cut from pilot: standalone /v1/search, raw filings, salary-by-title,
    batch, webhooks. /v1 additive-only once users exist. Errors always
    `{"error": "...", "hint": "..."}`.
11. **Quotas**: 500/day per key (X-Quota-Remaining header, midnight UTC
    reset); demo 30/day/IP; loud 429 with reset hint. Revisit only from logs.
12. **Engagement metrics** (documented SQL in README): signups/week,
    activation rate (signup -> >=1 real call), weekly-active keys, top queried
    employers. Landing funnel via SimpleAnalytics. Request log in Postgres:
    timestamp, endpoint, query, key id, user agent.
13. **Stack**: Python 3.12, FastAPI + uvicorn, stdlib sqlite3 (aggregates) +
    psycopg (user data), openpyxl read-only streaming for ETL, Resend via
    plain HTTPS, pytest + ruff, GitHub Actions deploy.
14. **Free-tier add-ons (GitHub Student Pack)**: Name.com free .dev domain,
    Sentry (errors), Datadog Pro (monitoring — also an AI-obs portfolio
    artifact), Honeybadger (ETL cron watchdog), SimpleAnalytics (landing),
    Testmail (OTP e2e tests in CI), Codecov, Stripe fee waiver (future paid
    tier). Rejected: Clerk (web-session oriented; hand-rolled OTP is
    curl-first and lock-in free), DigitalOcean credit (expiry ambiguity, no
    volumes on App Platform), Doppler/Travis/New Relic (redundant).

## Repo layout (current)

```
app/              main.py, auth.py, signal.py, quotas.py, db.py, lookup.py, landing.html
etl/              build.py, column_maps.py, sources.py, download.py, manifest.json
scripts/          build_data.py, smoke.py, heroku_bootstrap.py
bin/              post_compile (Heroku buildpack hook)
tests/            signal, ETL, API, lookup, e2e, testmail (CI-gated), real_etl (skipped)
.github/workflows/  ci.yml, deploy.yml, etl.yml
docs/             adr/, deploy.md, future-considerations.md
Dockerfile / Procfile / app.json / runtime.txt
CONTEXT.md, PLAN.md, README.md
```

## Work completed (2026-07-07)

### Phase 1 — CP0–CP5 (implementation)

- Repo scaffold: `pyproject.toml`, `app/`, `etl/`, `Procfile`, `Dockerfile`, tests
- ETL: `build.py`, `column_maps.py`, `sources.py`, `canonicalize.py`; synthetic fixtures
- Signal logic: tiers, trend, denial rate; table-driven pytest
- API: six frozen routes, OTP auth, quotas, FTS5 lookup, landing page
- E2E: mock-email OTP → key → signal (`tests/test_e2e.py`)

### Phase 2b — deploy prep

- `app.json`, `runtime.txt`, `bin/post_compile`, release-phase Postgres init
- GitHub Actions: `ci.yml`, `deploy.yml`, `etl.yml` (quarterly cron)
- `etl/download.py`, `etl/manifest.json`, `scripts/build_data.py`, `scripts/smoke.py`
- `docs/deploy.md`, `scripts/heroku_bootstrap.py`
- `docs/future-considerations.md` (Sponsorly vs this API; integration deferred)

### Phase 3 — started

- Public GitHub repo created and pushed: `ixsx2/h1b-service`
- CI green: **31 passed, 2 skipped** (`test_real_etl`, `test_testmail_e2e`)
- Deploy workflow green; skips Heroku push until `HEROKU_*` secrets set
- CI fixes: no `secrets` in workflow `if` guards; `H1B_TESTING=1` disables rate limits in tests
- `/healthz` reports `data_db`; startup fails fast if aggregates SQLite missing

### Not done yet

- Real DOL/USCIS ETL validation (`tests/fixtures/real/` empty → `test_real_etl` skipped)
- Live Heroku deploy, custom domain, Resend DKIM, full OTP funnel on production URL
- Phase 4 monitoring (Sentry, Honeybadger, SimpleAnalytics on production)

## Phases

| # | Scope | Status |
|---|--------|--------|
| 1 | ETL (synthetic fixtures) + signal logic + local API + pytest | **Done** (2026-07-07) |
| 2 | Landing + OTP/key flow + Testmail e2e (CI job wired, skips without secrets) | **Done** |
| 2b | Deploy prep: Heroku manifest, GitHub workflows, ETL cron, smoke script | **Done** |
| 3 | Live deploy: Heroku + Postgres + `.dev` domain + Resend DKIM + funnel smoke | **In progress** — CI/deploy workflows green; no Heroku secrets yet |
| 4 | Monitoring (Sentry, Datadog, Honeybadger, SimpleAnalytics) + publish | Not started |

## Next steps (priority order)

### Ishan — unblocks live URL

1. Pick public name; redeem Name.com `.dev` domain (Student Pack)
2. `heroku login` → create app + Postgres → set GitHub secrets (`HEROKU_API_KEY`, `HEROKU_APP_NAME`, `HEROKU_EMAIL`) — see `python scripts/heroku_bootstrap.py`
3. Re-run **Deploy** workflow or push to `master`
4. Resend account + DKIM on domain → `RESEND_API_KEY`, `EMAIL_FROM` on Heroku
5. `heroku domains:add` + Name.com DNS
6. Full smoke: `python scripts/smoke.py --base-url https://yourname.dev --email … --otp-code …`

### Either — before calling production "live"

7. Download FY2025/FY2026 DOL xlsx + USCIS CSV → `tests/fixtures/real/`; update `etl/manifest.json`
8. `pytest tests/test_real_etl.py -v` then redeploy (real `h1b_data.db` in slug)
9. Testmail secrets → CI runs real OTP e2e

### After live — Phase 4

10. `SIMPLE_ANALYTICS=1`, Sentry, Honeybadger ETL check-in
11. Publish; track engagement SQL from README

## Blocked on Ishan (Phase 3 remainder)

- ~~Create public GitHub repo (`github.com/ixsx2/h1b-service`) and push~~ **Done**
- Pick public name + redeem Name.com `.dev` domain from Student Pack
- Redeem Heroku credit; create Heroku app (`python scripts/heroku_bootstrap.py` for commands)
- Create Resend account; set `RESEND_API_KEY` + `EMAIL_FROM` after DKIM
- Redeem Testmail; set `TESTMAIL_API_KEY` + `TESTMAIL_NAMESPACE` GitHub secrets
- Paste USCIS CSV URL into `etl/manifest.json` (DOL URLs templated; verify after OFLC releases)
- Optional: `HONEYBADGER_ETL_CHECKIN_URL` for quarterly ETL watchdog

Checklist: [docs/deploy.md](docs/deploy.md). GitHub secrets for deploy:
`HEROKU_API_KEY`, `HEROKU_APP_NAME`, `HEROKU_EMAIL`.

Future integration with Sponsorly / Sponsor Check: [docs/future-considerations.md](docs/future-considerations.md).

## Verification bar before "live"

Unit tests green; ETL column maps validated against real files; deployed-URL
OTP->key->signal flow exercised end-to-end; engagement SQL documented in
README; Honeybadger alarm on the quarterly ETL confirmed firing on a forced
failure.
