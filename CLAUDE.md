# H1B Data Service — Working Instructions

Public-ready pilot API: "would this company sponsor an H-1B?" built from DOL
LCA disclosure files + USCIS Employer Data Hub.

**Status:** Phase 1 + deploy prep complete (2026-07-07). **Next:** Phase 3 live
deploy — blocked on Ishan's domain, GitHub remote, Heroku app, Resend, Testmail.
See [docs/deploy.md](docs/deploy.md).

## Read before working (in this order)

1. `PLAN.md` — settled decisions, frozen API surface, tier thresholds, phases.
2. `CONTEXT.md` — domain glossary (Canonical Employer, Signal Tier, etc.).
3. `docs/adr/` — recorded decisions; contradict only by superseding an ADR.
4. `docs/deploy.md` — when touching CI/CD, Heroku, or secrets wiring.

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

Every change lands with tests (pytest; ruff clean). Current: **31 passed, 2
skipped** (real ETL, Testmail e2e). Signal-tier and lookup-semantics changes
need table-driven cases. Testmail OTP e2e runs in CI when
`TESTMAIL_API_KEY` + `TESTMAIL_NAMESPACE` secrets are set. Before Phase 3 is
called done: live funnel smoke on the deployed URL (visit → demo → signup →
key → signal); ETL column maps validated against real DOL/USCIS files.

## Engagement (why the pilot exists)

Metrics and their SQL live in `README.md`: signups/week, activation rate,
weekly-active keys, top queried employers. Any feature proposal should say
which of these it moves.
