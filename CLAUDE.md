# H1B Data Service — Working Instructions

Public-ready pilot API: "would this company sponsor an H-1B?" built from DOL
LCA disclosure files + USCIS Employer Data Hub.

**Status (2026-07-07):** Phases 1–2b **done**. Phase 3 **in progress** — repo
https://github.com/ixsx2/h1b-service, CI green (31 passed). Live deploy blocked
on Heroku app + Resend + `.dev` domain. Next: [PLAN.md § Next steps](PLAN.md#next-steps-priority-order).

## Read before working (in this order)

1. `PLAN.md` — settled decisions, phase status, **work completed**, **next steps**.
2. `CONTEXT.md` — domain glossary (Canonical Employer, Signal Tier, etc.).
3. `docs/adr/` — recorded decisions; contradict only by superseding an ADR.
4. `docs/deploy.md` — Heroku, GitHub secrets, DNS, smoke tests.
5. `docs/future-considerations.md` — Sponsorly vs this API; integration deferred.

## Hard rules

- **This repo is public.** No JobApps content, no personal data, no tokens or
  keys in code, commits, or fixtures. Secrets live in Heroku config vars and
  a local `.env` (gitignored).
- **Zero imports from `Projects\JobApps`.** Shared logic (e.g. employer-name
  suffix stripping) is copied in, never imported. JobApps integration was
  explicitly deferred — do not wire it up unprompted.
- **The API surface is frozen at the six routes in PLAN.md.** Additive changes
  only once users exist; new routes need Ishan's sign-off.
- **Grade, never score.** The Sponsorship Signal is a tier; do not add numeric
  scores or fold trend/denial rate into the tier.
- **Replaceable data ships with code; irreplaceable data lives in Postgres**
  (ADR-0001). The ETL must never be able to touch user tables.
- **`matched: false` is not tier NONE**, and it is never cached.
- Cost/UX tradeoffs: baseline free, but paid option wins when it removes
  user-visible friction (Ishan's standing rule).

## Verification bar

Every change lands with tests (pytest; ruff clean). **CI:** 31 passed, 2 skipped.
Skipped: `test_real_etl` (no real DOL/USCIS files), `test_testmail_e2e` (no
Testmail secrets). `H1B_TESTING=1` in CI disables OTP/demo rate limits.

**Phase 3 done when:** Heroku URL serves demo + OTP → key → `/v1/signal`;
real-file ETL validated; engagement SQL runnable on production Postgres.

## Engagement (why the pilot exists)

Metrics and their SQL live in `README.md`: signups/week, activation rate,
weekly-active keys, top queried employers. Any feature proposal should say
which of these it moves.
