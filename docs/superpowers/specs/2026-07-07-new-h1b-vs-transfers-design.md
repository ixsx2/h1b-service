# Design: new_h1b vs transfers signal split

Date: 2026-07-07. Status: approved in conversation (Ishan), pending spec review.

## Problem

The USCIS denial-rate enrichment pooled all "initial" petitions into one number.
Ishan identified that **Change of Employer (COE)** — an employer taking on a
worker who already holds H-1B — signals a different willingness than fresh/cap
sponsorship (New Employment). A company can be transfer-heavy but never file a
fresh cap petition; merging the two misleads exactly the candidate the signal
serves. Measured volumes confirm COE is material: 18.1% of FY2026 approvals
(28,709), 78,494 in FY2020 (64% the size of fresh).

## Decision (supersedes the interim COE-merge)

Report two separate USCIS categories; never merge them:

- **new_h1b** = New Employment + New Concurrent (fresh/cap sponsorship).
  Empirically verified identical to the legacy export's `Initial Approval`
  (FY2020: 122,894 = 121,874 + 1,020, exact match).
- **transfers** = Change of Employer only (will-hire-existing-H1B).

Excluded from both, as same-employer renewals/tweaks: Continuation, Change
with Same Employer, Amended.

The Signal Tier and trend remain purely LCA-driven — untouched.

## Data sources (verified 2026-07-07)

`data/sources/Employer Information_{2020..2023,2024-2026}.xlsx` — all five
carry the full 20-column split petition-type schema for FY2020–FY2026
(~393K rows). Legacy 4-column CSVs deleted after verifying equivalence
(FY2026 CSV ≡ consolidated xlsx on NewEmp and COE totals). USCIS `Tax ID`
is last-4-digits by design (glossary) — name canonicalization remains the
only DOL↔USCIS join key. USCIS rows are pre-aggregated per
(FY, NAICS, TaxID, state, city, ZIP): one employer = many rows; ingest must
sum per canonical name. Number cells may be comma-formatted strings.

## Schema (aggregates table)

Replace `uscis_initial_approvals/denials` with:

```
uscis_new_approvals      INTEGER NOT NULL DEFAULT 0
uscis_new_denials        INTEGER NOT NULL DEFAULT 0
uscis_transfer_approvals INTEGER          -- NULL = breakout unavailable
uscis_transfer_denials   INTEGER          -- NULL = breakout unavailable
```

No migration: the aggregates DB rebuilds from scratch each ETL (ADR-0001).
NULL means "this vintage can't say", never 0. With current files the NULL
path is a safety valve for future format drift, not an active case.

## Column maps

`UscisColumns` carries four tuples: `new_approval_columns`,
`new_denial_columns`, `transfer_approval_columns`, `transfer_denial_columns`.
Empty transfer tuples = breakout unavailable → NULLs. `USCIS_DATA_HUB` maps
the split schema; `USCIS_STANDARD`/`USCIS_LOWER` (legacy/fixture, pre-summed
`Initial`) keep transfer tuples empty. The interim change that added COE to
`approval_columns` is reverted by this design.

## Ingest

USCIS ingest switches to xlsx (openpyxl read-only streaming, like DOL):
`build_data.py` picks up `Employer Information*.xlsx` for USCIS. CSV path
retained for legacy compatibility. Comma-tolerant int parsing. Blank employer
names skipped (glossary: data-entry errors occur).

## Signal payload (frozen-API amendment to PLAN.md #10)

```json
"signal": {
  "tier": "...",                    // unchanged
  "trend": "...",                   // unchanged
  "new_h1b":   { "approvals": N, "denials": N, "denial_rate": F|null, "caution": B },
  "transfers": { "approvals": N, "denials": N, "denial_rate": F|null, "caution": B } | null,
  "certified_by_year": [...],       // unchanged
  "latest_complete_fy": N           // unchanged
}
```

- Per-category denial math: `denials / (approvals + denials)`; `denial_rate`
  null when decisions < `DENIAL_MIN_PETITIONS` (10); caution at >= 15%.
  Thresholds applied independently per block.
- Both blocks read the `latest_complete_fy` row (2025 — populated now that
  USCIS covers 2020–2026).
- `transfers: null` (whole block) only when the vintage lacks the breakout.
- **Clean break**: flat `denial_rate`/`denial_caution` removed, no alias.
  No users exist; a duplicate top-level rate would reintroduce the
  fresh-vs-transfer conflation this design removes.
- `/v1/employer/{name}` per-FY rows expose the four new fields, replacing
  `uscis_initial_*`.

## Landing page

Demo card renders two labeled rows — "New H-1B (fresh/cap)" and
"Transfers (already on H-1B)" — replacing the single denial-rate line.
JSON tab shows the raw payload.

## Validation stage (pre-build gate, Ishan's addition)

Before the full ~85-min build, a subset smoke run:

1. Sample ~5 anchors (Google, Amazon, Infosys, a Deloitte entity, one small
   employer) + ~10 randomly drawn employer names.
2. Independent recomputation: a throwaway script sums new_h1b/transfers from
   raw xlsx rows (separate code path from the ingest) and must match the
   ingest's buckets — catches column-index, comma-parsing, multi-row
   summation, and blank-name bugs.
3. Cross-vintage identity: FY2020 legacy `Initial` total (122,894) must equal
   ingested NewEmp+NewConc through the real ingest path.
4. Join check with one DOL file (FY2025_Q4): sampled companies get LCA counts
   on the same canonical key.
5. All pass → full build; any fail → stop.

USCIS files are small (seconds to parse); only DOL files are slow, hence the
one-quarter subset.

## Tests

- Signal: per-block threshold cases (e.g. 8 fresh + 40 transfer decisions →
  new_h1b.denial_rate null, transfers real), whole-block-null case.
- ETL: split-schema xlsx fixture; multi-row-per-employer summation; comma
  numbers; legacy pre-summed path yields transfer NULLs.
- API: payload shape assertions; e2e updated.

## Docs

- CONTEXT.md: add **New Sponsorship** and **Transfer** glossary terms.
- PLAN.md: amend decision #10 (payload shape), log the work.
- This spec supersedes the "initial = NewEmp+NewConc+COE" interim decision.

## Out of scope

Entity resolution for multi-entity filers (Deloitte fragmentation), FY2024
DOL↔USCIS orphan-rate measurement (runs after rebuild), historical FY<2020
data.
