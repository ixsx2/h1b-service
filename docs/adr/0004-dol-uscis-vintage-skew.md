# DOL and USCIS vintages are tracked separately and labelled per field

DOL LCA data refreshes quarterly; the USCIS Employer Data Hub refreshes roughly
yearly and lags. So at any moment the latest complete DOL fiscal year can be
ahead of the latest complete USCIS fiscal year. A single `latest_complete_fy`
would silently make one source's data describe a year the other has not
published — the Signal Tier (DOL certified counts) and the denial blocks (USCIS
approvals/denials) would describe different time windows while appearing aligned,
and the orphan census would flag every USCIS employer as orphaned for a year
USCIS never covered.

We decided to track the two vintages separately (`latest_dol_fy`,
`latest_uscis_fy` in `meta`), compute the tier at the latest DOL FY and the
denial blocks at the latest USCIS FY, and **label each field in the response
with its own fiscal year** so the skew is visible rather than assumed away. The
orphan census and the ship gate both run at `latest_uscis_fy` — the constrained
source — so matching is only ever measured over a year both sources cover.

The rejected alternative was pinning both to `min(latest_dol_fy,
latest_uscis_fy)`: one clean aligned window, no per-field FY labels, simpler.
Rejected because it discards the freshest DOL quarter, and the whole point of
the quarterly DOL cadence is currency of sponsorship *intent*.

## Consequences

- The Sponsorship Signal payload gains per-block fiscal-year labels; a client
  must not assume tier and denial data share a year.
- `latest_complete_fy` is replaced by the two split keys everywhere it is read
  (signal computation, orphan census, ship gate).
