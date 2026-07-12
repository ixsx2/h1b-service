# H1B Data Service

Public-ready API serving H-1B sponsorship history per employer, built from DOL
LCA disclosure files and the USCIS H-1B Employer Data Hub. Exists to answer one
question fast: "would this company sponsor an H-1B?"

## Language

**Canonical Employer**:
The normalized identity of an employer: suffix-stripped, punctuation-collapsed,
uppercased legal name that all filings roll up to. Original filed names map to
it via a lookup table.
_Avoid_: company, employer name (ambiguous — filed name or canonical?)

**Filed Name**:
An employer name exactly as it appears in a DOL or USCIS source row. Many filed
names map to one Canonical Employer.

**Employer-Year Aggregate**:
The unit of storage: one row per (Canonical Employer, fiscal year) holding
certified-LCA counts, salary stats, top titles, and USCIS approval/denial
counts. The service stores aggregates, not individual filings.
_Avoid_: record, filing (a filing is a source row, not what we store)

**Fiscal Year**:
The US federal fiscal year (Oct-Sep) used by both DOL and USCIS data. All
year-keyed data in the service means fiscal year, never calendar year.

**LCA (Labor Condition Application)**:
A DOL filing declaring intent to employ an H-1B worker. Certification is
near-automatic (~98%) and one hire can have several — LCA volume signals
intent, not outcomes.

**Petition**:
An I-129 request to USCIS to actually employ the worker. Approvals/denials come
from the USCIS Employer Data Hub. Petition outcomes signal real sponsorship.
_Avoid_: application (collides with LCA)

**Sponsorship Signal**:
The service's headline output for a Canonical Employer: a Signal Tier plus
supporting numbers (recent certified counts, trend, and the new_h1b/transfers
denial blocks). A grade, not a score.
_Avoid_: sponsor score (implies false numeric precision)

**Signal Tier**:
One of four grades on a Sponsorship Signal. ACTIVE: sponsors routinely in the
latest fiscal year. ESTABLISHED: sponsors, but latest-year volume is low or
lumpy. RARE: has sponsored within five years; confirm directly. NONE: no
certified LCAs in five years.

**Trend**:
Direction of certified-LCA volume, latest fiscal year vs the prior one:
rising, falling, or flat. Null when volumes are too small to mean anything.

**New Sponsorship (new_h1b)**:
USCIS petitions where the employer takes on a worker it did not previously
sponsor at all: New Employment + New Concurrent. Equals the legacy export's
single "Initial" column exactly. One of the two denial blocks on a Sponsorship
Signal.

**Transfer (transfers)**:
USCIS Change of Employer petitions: the worker already holds H-1B status and
moves to this employer. Signals willingness to hire existing H-1B holders even
when an employer files few or no fresh/cap petitions. Null (not 0) when the
source vintage has no breakout — never conflate "can't say" with "zero".
_Avoid_: reporting transfers folded into new_h1b (the distinction is the point).

**Denial Rate**:
Denials over decisions for a given denial block (new_h1b or transfers),
latest fiscal year. Computed independently per block. Null below a minimum
petition count — small denominators must not print as percentages. Caution
flag at >=15% with real volume.

**Orphan**:
A Canonical Employer present in only one source: USCIS approvals with no
matching DOL LCA row, or the reverse. Caused by the two sources spelling the
same employer differently (the join runs on name only — the FEIN join is dead).
An orphan is never graded: it returns a Partial Signal, not a Signal Tier.
_Avoid_: "missing" (an orphan has data, just from one side).

**Partial Signal**:
The response state for an Orphan: the numbers from the matched source, an
explicit `missing_source`, and a suppressed (null) Signal Tier. Distinct from
both a full match and `unmatched` (the query hit nothing at all). Extends the
rule "matched: false is not tier NONE" to half-matches — absence of a source is
never laundered into a grade.

**Vintage**:
The fiscal year a source's data is current through. DOL and USCIS refresh on
different cadences (DOL quarterly, USCIS ~yearly and lagged), so the latest DOL
Vintage can lead the latest USCIS Vintage. Each field in a Sponsorship Signal
carries its own Vintage; tier and denial data must not be assumed to share one.
_Avoid_: "latest year" (ambiguous across the two sources).
