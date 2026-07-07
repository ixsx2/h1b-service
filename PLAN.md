# H1B Data Service — Pilot Plan

Status: **Phase 1 complete** (CP0–CP5 landed 2026-07-07): ETL against synthetic
fixtures, signal logic, local API with six routes, landing + mock-email OTP e2e.
Real-file ETL validation test skips until DOL/USCIS files are placed in
`tests/fixtures/real/`. Phase 2 = deploy (Heroku, Postgres, Resend, .dev domain).
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

## Repo layout (target)

```
app/          FastAPI: main.py, auth.py, signal.py, quotas.py, db.py, landing.html
etl/          build.py, column_maps.py, sources.py
tests/        signal tiers, canonicalization, auth flow, quota edges
.github/workflows/  deploy.yml, etl.yml (quarterly cron)
Dockerfile / Procfile
CONTEXT.md, PLAN.md, README.md (written for strangers), docs/adr/
```

## Phases

1. ETL against real FY2025+FY2026 DOL/USCIS files locally + signal logic +
   local API + full pytest suite.
2. Landing page + OTP/key flow (Testmail-backed e2e tests).
3. Deploy: Heroku + Postgres + .dev domain + Resend DKIM; live smoke of the
   whole funnel (visit -> demo -> signup -> key -> signal call).
4. Wire monitoring (Sentry, Datadog, Honeybadger, SimpleAnalytics); publish;
   post for feedback.

## Blocked on Ishan (none block Phase 1)

- Redeem from Student Pack: Heroku credit, Name.com .dev domain (pick name),
  Testmail
- Create Resend account
- Create public GitHub repo (github.com/ixsx2/...) + Heroku app
- Pick the public name/domain

## Verification bar before "live"

Unit tests green; ETL column maps validated against real files; deployed-URL
OTP->key->signal flow exercised end-to-end; engagement SQL documented in
README; Honeybadger alarm on the quarterly ETL confirmed firing on a forced
failure.
