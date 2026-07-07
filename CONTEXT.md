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
supporting numbers (recent certified counts, trend, denial rate). A grade, not
a score.
_Avoid_: sponsor score (implies false numeric precision)

**Signal Tier**:
One of four grades on a Sponsorship Signal. ACTIVE: sponsors routinely in the
latest fiscal year. ESTABLISHED: sponsors, but latest-year volume is low or
lumpy. RARE: has sponsored within five years; confirm directly. NONE: no
certified LCAs in five years.

**Trend**:
Direction of certified-LCA volume, latest fiscal year vs the prior one:
rising, falling, or flat. Null when volumes are too small to mean anything.

**Denial Rate**:
USCIS initial denials over initial decisions for the latest fiscal year. Null
below a minimum petition count — small denominators must not print as
percentages.
