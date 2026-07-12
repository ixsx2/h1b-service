# Design: DOL↔USCIS entity resolution

Date: 2026-07-08. Status: approved in conversation (Ishan), pending spec review.

**Amended 2026-07-12** (grill-with-docs session): ceiling set to marquee-correct
(ADR-0002), orphan employers return a `partial` state (ADR-0003), DOL/USCIS
vintage skew tracked per-field (ADR-0004), plus four refinements to the ship
gate, alias durability, merge-safety, and the published orphan metric — folded
into the sections below.

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

- **Punctuation → space**, not delete: `.` `,` `/` `(` `)` `-`. Current code
  deletes `.`, which is the exact bug splitting `AMAZON.COM` (→`AMAZONCOM`)
  from `AMAZON COM`. Replace mojibake (`�`, `\xa0`) with space.
- **Apostrophe → delete** (not space): `CHILDREN'S` must become `CHILDRENS`
  to converge with the apostrophe-free spelling (bake-off: 0.98–0.99 matches).
  Spacing it would produce `CHILDREN S` and split instead of merge.
- **Single-letter-run collapse** (after punctuation → space): runs of 2+
  adjacent single-letter tokens merge into one token — `U S A`→`USA`,
  `N A`→`NA`, `A T KEARNEY`→`AT KEARNEY`, `L P`→`LP`. Required because
  dot→space alone would *break* pairs the old dot-delete happened to merge
  (verified: `VISA U.S.A.` and `VISA USA` both canonicalize to `VISA USA`
  today; dot→space without collapse splits them into `VISA U S A` vs
  `VISA USA`). The collapse never crosses a multi-letter token, so
  `AMAZON COM` is untouched.
- **`&` → ` AND `** (that direction, with surrounding spaces), then collapse
  whitespace; drop a dangling trailing `AND`. Gives `TEXAS A&M` →
  `TEXAS A AND M` (= USCIS's spelling) and `JPMORGAN CHASE & CO` →
  `JPMORGAN CHASE` (CO suffix-stripped, trailing AND dropped) =
  USCIS's `JPMORGAN CHASE AND`.
- **`D B A` / `DBA` clause truncate** to the legal filer before it (13,989
  occurrences; FIDELITY GROUP D B A FIDELITY INVESTMENTS → FIDELITY GROUP).
  Guard: if the clause starts the name (nothing before it), keep the name
  unchanged rather than canonicalizing to empty.
- **Extend suffix strip**: add `PC PLLC LLP LP PA` — **trailing position
  only**, unlike the existing anywhere-in-name `INC LLC CORP …` set. Two-letter
  tokens are too likely to be meaningful mid-name (`PC CONNECTION`,
  `LP BUILDING SOLUTIONS`) to strip positionally blind.
- **Strip leading `THE`** (6,223 names; THE BOEING COMPANY → BOEING COMPANY).

**Explicitly NOT stripped** — false-merge traps, deferred to Layer 2: trailing
`USA` / `US` / `AMERICA` / `AMERICAS`, `HOLDINGS`, `GROUP`, and other
geographic/word suffixes. Stripping trailing `AMERICA` would merge
`BANK OF AMERICA` into `BANK OF`. The bake-off showed these are exactly where a
blind rule breaks (AMAZON COM → AMAZON WEB SERVICES at 0.84 is wrong).

Layer 1 changes the canonical key for both DOL and USCIS filings identically,
so matched pairs converge with zero curation.

### Layer 2 — curated alias map (`etl/aliases.csv`)

- **`etl/aliases.csv`**: columns `source_canonical,target_canonical,note`
  (the `note` provenance column added 2026-07-12 — a per-row breadcrumb such as
  `worksheet-2026-07-11` or `manual:UMASS=UMass Chan`, so a future reviewer can
  audit *why* a merge exists without re-deriving it), a header comment stating
  file-level provenance, committed and human-reviewed. The two key columns hold
  **post-Layer-1 canonical keys** (i.e. the output of `canonicalize()`, not raw
  filed names). Applied in `build_from_paths` after `canonicalize()`
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
  report exists so any false merge the rule changes introduce is visible. It
  stays a report (for discovering *new* collisions), not a gate — the durable
  fence for *known* traps is the golden suite below.
- **Golden canonicalize regression suite (2026-07-12)** — a curated, two-sided
  pair list run in CI on every Layer-1 change: **must-stay-distinct**
  (`BANK OF AMERICA ≠ BANK OF`, `AMAZON ≠ AMAZON WEB SERVICES`,
  `PENN STATE ≠ UNIVERSITY OF PENNSYLVANIA`, …) and **must-merge**
  (`AMAZON.COM = AMAZON COM`, …). Each entry is a trap the bake-off already paid
  to discover; the suite freezes them so a future rule tweak cannot silently
  un-fix one. Replaces the unrepeatable "eyeball the 2 MB collisions report"
  step. Grow it whenever a new trap is found.
- **Dead-alias gate (2026-07-12)** — at build time, any `aliases.csv` row whose
  `source_canonical` never occurs in the ingested corpus is a **dead alias**.
  Because alias keys are post-Layer-1 canonicals, a future normalization-rule
  change can silently orphan an entry, regressing a merge with no error. A dead
  alias is always a bug: either the rule changed (re-curate) or the entity
  vanished (delete the row). Promoted from warning to a CI gate
  (`test_no_dead_aliases`, active when real data is present).

## Ship criterion (the gate)

- **`test_known_sponsors_join`** — a fixed allowlist of marquee employers
  (Amazon, Google, the big consultancies, top banks, top universities). Each
  must have `certified_count > 0` AND `uscis_new_approvals > 0` at
  `latest_uscis_fy`. Any red = ship blocker. This guarantees the high-stakes
  names a user is likeliest to query are correct, without chasing a global
  percentage.

  **Hardened (2026-07-12):** presence-only proves the two sources *joined*, not
  that the join is *correct* — a wrong merge into a small bucket leaves both
  counts non-zero and passes green. Two additions:
  1. **Magnitude bands, not just presence.** Each marquee name asserts its
     counts fall in a reviewed order-of-magnitude band (Amazon's certified LCAs
     are thousands, not 12). Catches wrong-merge-into-small-bucket and
     split-not-merged.
  2. **Data-derived allowlist.** The allowlist is the hand-picked marquee set
     **unioned with the top-N USCIS employers by approval volume** at
     `latest_uscis_fy`, so the gate covers the names that dominate the *numeric*
     error surface, not only the ones we remembered.
- **Orphan metric (published).** The **approval-weighted** orphan rate is the
  single public honesty metric ("N% of H-1B approvals sit on employers we could
  not cross-match"). It is logged to `meta` each build and is observability,
  NOT a gate. The key-weighted rate stays internal (a curation-progress number;
  driving it down chases tiny firms, which ADR-0002 declines). Query-weighted
  orphan rate is the post-launch curation compass once engagement data exists.

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
