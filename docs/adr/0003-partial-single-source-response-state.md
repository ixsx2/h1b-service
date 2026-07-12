# Orphaned employers return a partial state, never a tier computed on half the data

An orphaned employer (matched in only one source) does not surface as missing
data — it surfaces as a *confident wrong grade*. A USCIS-only Amazon has
`certified_count = 0`, so the tier logic grades it RARE while it shows thousands
of real approvals. We decided an orphan must **suppress the Signal Tier** and
return an explicit `partial` (single-source) response: show the numbers we do
have, set `tier: null`, and name the missing source. This extends the existing
"`matched: false` is not tier NONE" principle to half-matches — the same refusal
to let absence of data masquerade as a grade.

The rejected alternative was to keep computing a tier from whichever source
matched and footnote "USCIS data not found." Simpler (no new state), but it lets
a top sponsor display as RARE, which is exactly the confident-wrong-answer the
service exists to avoid.

## Consequences

- `/v1/signal` uses a discriminated union on a `status` field:
  `matched` | `partial` | `unmatched` | `candidates`, replacing the boolean
  `matched` flag. `partial` carries `missing_source` and `tier: null`.
- Caching: `partial` caches like `matched` (a real, stable answer until the next
  quarterly ETL); only `unmatched` stays uncached (a near-miss may resolve as
  data grows). See the entity-resolution spec.
- Safe to reshape the contract now: the pilot has no live API consumers.
