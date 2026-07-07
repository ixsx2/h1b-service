# Future considerations — Sponsorly vs h1b-service

Captured 2026-07-07 for integration and positioning decisions. Do not re-litigate
pilot API semantics here; this doc is strategic context only.

## Two layers, one problem

| Layer | Project | Optimizes for |
|-------|---------|----------------|
| **Presentation + JD intelligence** | [Sponsorly](https://sponsorly.dev/) / Sponsor Check | Job seeker on the job page (Chrome extension, 16+ ATS scrapers) |
| **Canonical employer signal** | h1b-service (this repo) | Correct, auditable DOL LCA + USCIS aggregates via API |

Same user question ("will this company sponsor?") but different moments:

- **On a posting:** regex + LLM on JD text + employer history → fast verdict
- **By company name:** tier + trend + denial rate → reproducible grade, no AI in core path

## Sponsorly approach (strengths)

- **Distribution:** extension where users already are (LinkedIn, Workday, Greenhouse, etc.)
- **JD signal:** 40+ negative / 15+ positive heuristics + Mistral/Llama on full description
- **Three independent signals:** regex (deterministic) + AI (nuance) + H1B history (ground truth)
- **Product UX:** per-signal confidence, color-coded verdict, &lt;5s flow
- **Full-stack portfolio story:** scraping, NLP entity extraction, ETL, FastAPI, Supabase, MV3

## Sponsorly approach (risks)

1. **Fused questions** — JD exclusion language ≠ company never sponsors; silent JD ≠ no history. Collapsing into one "97% sponsors" score overstates certainty.
2. **Data vintage** — public site cited DOL 2021–2023 (stale by 2026); freshness must be explicit in product and resume.
3. **Ops surface** — per-ATS scrapers drift; LLM + fuzzy employer match need ongoing maintenance.
4. **False precision** — "probability" without definition is hard to defend (LCA ≠ petition ≠ this role).

## h1b-service approach (strengths)

- **Grade, never score** — ACTIVE / ESTABLISHED / RARE / NONE (PLAN.md frozen)
- **USCIS denial rate** — differentiator vs most lookup tools
- **Conservative lookup** — `matched: false` ≠ tier NONE; no auto-pick on fuzzy hits
- **curl-first API** — integrators, portfolio reviewers, scripted clients
- **Low ops** — quarterly ETL → immutable `h1b_data.db` in slug; user data in Postgres only

## h1b-service approach (limits)

- No browser distribution; no JD text analysis; not answering "this posting" without an integrator.
- Phase 3 deploy still needs domain, Resend, Heroku secrets (see [deploy.md](deploy.md)).

## Recommended evolution (deferred — not in pilot scope)

Per PLAN.md: **zero imports from JobApps**; **no unprompted Sponsorly/Sponsor Check wiring**.

When integration is explicitly approved:

```
Job page (extension) ──► POST/GET company name ──► h1b-service /v1/signal
                              │
                              ├── tier, trend, denial_rate (employer history leg)
                              └── Keep JD regex/AI verdict separate in UI (do not fold into tier)
```

**Entity resolution:** extension extracts "Acme Corp" from page → API canonicalizes to
`ACME` via filed-name / FTS5 lookup → return `matched_as` when needed.

**UI contract:** show three legs independently (same as Sponsorly today):

1. Regex/AI on posting (client or separate service)
2. Employer Signal Tier from this API
3. Optional: denial caution flag from USCIS join

Do **not** merge JD confidence % into Signal Tier.

## Gaps to close on Sponsorly side (for interview/product credibility)

- [ ] Refresh DOL/USCIS data to last 5 complete fiscal years (align with this ETL)
- [ ] Define what "probability" / "confidence" means per signal in UI copy
- [ ] Surface data vintage on every history-backed answer
- [ ] Split "posting says no" vs "company has no filings" in the verdict card

## References

- Sponsorly product: https://sponsorly.dev/
- Sponsor Check API (legacy): `api.sponsorcheck.work`
- This repo pilot plan: [PLAN.md](../PLAN.md)
- Deploy checklist: [deploy.md](deploy.md)
