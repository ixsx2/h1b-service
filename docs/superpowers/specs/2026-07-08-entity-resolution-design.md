# Design: DOL↔USCIS entity resolution

Date: 2026-07-08. Status: approved in conversation (Ishan), pending spec review.

## Problem

DOL LCA and USCIS Employer Data Hub are joined on `canonicalize()` of the
employer name — the only usable key, because USCIS publishes just the last four
digits of the Tax ID (FEIN join is dead, measured). The two sources spell the
same employer differently, so the join misses badly.

Measured on the live FY2020–2026 build (`data/h1b_data.db`):

- 197,947 distinct DOL names, 173,224 distinct USCIS names, canonicalizing to
  210,585 keys — barely below either source, so current normalization is *not*
  merging cross-source pairs. A tight join would land far lower.
- **17–32% of fresh USCIS approvals per FY sit on orphan keys** (no LCA row):
  162,730 orphan approvals across 52,872 keys, FY2020–2026. FY2025: 21.1%.
- Plus ~457 reverse orphans (ACTIVE-scale LCA employers with zero USCIS row).

User-facing impact is worse than a missing number: a top sponsor like Amazon
splits into `AMAZONCOM SERVICES` (DOL side, tier ACTIVE, 15,494 certified LCAs,
but new_h1b/transfers = 0/0, denial rates null) and `AMAZON COM SERVICES`
(USCIS side, tier RARE because certified=0, but 3,010 fresh approvals). Neither
record tells the truth; a user sees an ACTIVE employer with blank outcome data
or a RARE one with thousands of approvals.

## Orphan cause census (FY2025, approval-weighted)

Bucketed all 7,176 FY2025 orphans by cause:

| Class | Keys | Approvals | % orphan appr |
|---|---|---|---|
| space/dot (AMAZON COM vs AMAZON.COM) | 410 | 5,788 | 23.9% |
| &/and (JPMORGAN CHASE AND) | 562 | 3,416 | 14.1% |
| &/and + space | 38 | 773 | 3.2% |
| DBA (FIDELITY … D B A …) | 1,561 | 4,190 | 17.3% |
| true-distinct / abbrev / subsidiary | 4,605 | 10,024 | 41.4% |

The first four (58.6%) are deterministic normalization gaps. The last (41.4%)
needs real resolution — and a token census across all 433K filed names plus a
fuzzy bake-off on the top 150 orphans confirmed which rules are safe vs which
are false-merge traps (below).

## Decision: two layers, curated merges only

Never auto-merge. Every cross-entity merge is either a deterministic
normalization rule (safe by construction) or a human-reviewed alias entry.
False-merge (joining two genuinely distinct employers) is worse than an orphan.

### Layer 1 — deterministic normalization (`etl/canonicalize.py`)

Rules chosen from the 433K-name token census and validated against the fuzzy
bake-off (each was a high-confidence, correct match class):

- **Punctuation → space**, not delete: `.` `,` `/` `(` `)` `-` and apostrophe
  (`'`). Current code deletes `.`, which is the exact bug splitting
  `AMAZON.COM` (→`AMAZONCOM`) from `AMAZON COM`. Bake-off: apostrophe cases
  score 0.98–0.99 (ST JUDE CHILDRENS = CHILDREN'S). Strip mojibake
  (`�`, `\xa0`).
- **`&` / `AND` unify** to one token, drop a dangling trailing `AND`
  (JPMORGAN CHASE AND = JPMORGAN CHASE &).
- **`D B A` / `DBA` clause truncate** to the legal filer before it (13,989
  occurrences; FIDELITY GROUP D B A FIDELITY INVESTMENTS → FIDELITY GROUP).
- **Extend suffix strip**: add `PC PLLC LLP LP PA` to the existing
  `INC LLC CORP …` set. Entity-form markers only.
- **Strip leading `THE`** (6,223 names; THE BOEING COMPANY → BOEING COMPANY).

**Explicitly NOT stripped** — false-merge traps, deferred to Layer 2: trailing
`USA` / `US` / `AMERICA` / `AMERICAS`, `HOLDINGS`, `GROUP`, and other
geographic/word suffixes. Stripping trailing `AMERICA` would merge
`BANK OF AMERICA` into `BANK OF`. The bake-off showed these are exactly where a
blind rule breaks (AMAZON COM → AMAZON WEB SERVICES at 0.84 is wrong).

Layer 1 changes the canonical key for both DOL and USCIS filings identically,
so matched pairs converge with zero curation.

### Layer 2 — curated alias map (`etl/aliases.csv`)

- **`etl/aliases.csv`**: two columns `source_canonical,target_canonical`, a
  header comment stating provenance, committed and human-reviewed. Both columns
  hold **post-Layer-1 canonical keys** (i.e. the output of `canonicalize()`,
  not raw filed names). Applied in `build_from_paths` after `canonicalize()`
  and before bucketing: any filed name whose post-canonical key equals
  `source_canonical` is remapped to `target_canonical`. Only entries in this file ever merge; nothing automatic.
- **`scripts/generate_alias_worksheet.py`**: ranks orphans by approval volume,
  blocks each against LCA-side names by shared first token, scores with stdlib
  `difflib.SequenceMatcher`, and emits `worksheet.csv`
  (`orphan,suggestion,score,approvals,accept`) for human review. The reviewer
  fills `accept`; accepted rows are filtered into `aliases.csv`. The suggester
  proposes; it never merges. Bake-off evidence: fuzzy-block gives high recall on
  the real orphan set but ~15–20% of high-scoring suggestions are wrong-same
  (Amazon→AWS, Penn→Montana), so human confirmation is mandatory.

The ~30% of orphans with no similar LCA string at all (UMASS CHAN MEDICAL
SCHOOL = University of Massachusetts, PWC ADVISORY = PricewaterhouseCoopers)
get no fuzzy suggestion; they are matched manually from knowledge or left as
documented orphans. An LLM suggester for these is out of scope for the pilot.

## Guards

- **`normalization_collisions.csv`** — emitted at build time. Lists every new
  canonical key that receives filed names the *old* normalizer kept as 2+
  distinct keys, ranked by approvals. Most collisions are correct merges; the
  report exists so any false merge the rule changes introduce is visible and
  eyeballed before the build is trusted. A report, not a gate.

## Ship criterion (the gate)

- **`test_known_sponsors_join`** — a fixed allowlist of ~40 marquee employers
  (Amazon, Google, the big consultancies, top banks, top universities). Each
  must have `certified_count > 0` AND `uscis_new_approvals > 0` at the latest
  complete FY. Any red = ship blocker. This guarantees the high-stakes names a
  user is likeliest to query are correct, without chasing a global percentage.
- The approval-weighted orphan rate is logged to the aggregates `meta` table
  each build as observability, NOT a gate.

## Data flow

```
raw filed name
  -> canonicalize()  [Layer 1 rules]
  -> alias remap     [Layer 2, if key in aliases.csv]
  -> bucket by (final canonical, fiscal year)
```

Both DOL and USCIS ingest paths run the same two steps, so a DOL "AMAZON.COM
SERVICES" and a USCIS "AMAZON COM SERVICES" land on the same bucket.

## Schema / build

No schema change: the aggregates DB rebuilds from scratch each ETL (ADR-0001),
so the new normalization + alias map simply produce different canonical keys.
`aliases.csv` ships with the code (replaceable data, per ADR-0001). ETL never
touches user tables.

## Testing

- **Layer 1 unit tests** (`tests/test_canonicalize.py` or extend
  `test_etl.py`): one per rule — dot→space, apostrophe strip, `&`/`AND` unify +
  dangling drop, DBA truncate, new suffixes (PC/PLLC/LLP/LP/PA), leading THE.
  Plus explicit false-merge guards: `BANK OF AMERICA` canonicalizes distinct
  from `BANK OF`; `AMAZON.COM` and `AMAZON COM` canonicalize equal.
- **Alias application test**: a fixture `aliases.csv` remaps a source key to a
  target and the bucket lands on the target.
- **Ship-gate test**: `test_known_sponsors_join` over the allowlist (runs
  against the real build; skipped in CI without real data, like `test_real_etl`).

## Out of scope

LLM suggester for no-candidate orphans; any auto-merge (fuzzy, embedding,
clustering); external crosswalks (SEC EDGAR, OpenCorporates, GLEIF, D&B);
FEIN join (dead — USCIS ships 4-digit Tax ID); reverse-orphan resolution
(LCA employers with no USCIS row — measured but deferred).

## Implementation order

1. Layer 1 rules in `canonicalize()` + unit tests (including false-merge
   guards). Rebuild, re-run orphan measurement, record the new rate.
2. `normalization_collisions.csv` guard in the build; eyeball top collisions.
3. `aliases.csv` (empty + header) + apply step in `build_from_paths` + test.
4. `scripts/generate_alias_worksheet.py`; run it, review, populate `aliases.csv`
   for the top orphans by volume. Rebuild.
5. `test_known_sponsors_join` allowlist; iterate aliases until green.
6. Orphan-rate to `meta`; PLAN.md + CONTEXT.md updates (Canonical Employer term
   now spans a normalization + alias step).
