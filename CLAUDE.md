# H1B Data Service — Working Instructions

Public-ready pilot API: "would this company sponsor an H-1B?" built from DOL
LCA disclosure files + USCIS Employer Data Hub. Status: **Phase 1 complete**
(CP0–CP5: scaffold, ETL, signal logic, local API, landing + OTP e2e). Next:
deploy to Heroku.

## Read before working (in this order)

1. `PLAN.md` — all settled decisions, frozen API surface, tier thresholds,
   quotas, phases. Decisions there were grilled one-by-one; do not re-litigate
   without new information — propose a change explicitly instead.
2. `CONTEXT.md` — domain glossary. Use these terms exactly (Canonical
   Employer, Filed Name, Employer-Year Aggregate, Signal Tier, Trend, Denial
   Rate). New/changed concepts get added there when they crystallize.
3. `docs/adr/` — recorded decisions with reasoning. Contradicting an ADR
   requires updating or superseding it, never silent deviation.

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

Every change lands with tests (pytest; ruff clean). Signal-tier and
lookup-semantics changes need table-driven cases. The OTP flow has
Testmail-backed e2e tests in CI. Before any deploy is called done: live
funnel smoke on the deployed URL (visit -> demo -> signup -> key -> signal).

## Engagement (why the pilot exists)

Metrics and their SQL live in `README.md` once built: signups/week,
activation rate, weekly-active keys, top queried employers. Any feature
proposal should say which of these it moves.
