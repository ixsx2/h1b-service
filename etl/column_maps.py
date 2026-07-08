"""Per-fiscal-year column name maps — DOL columns drift between releases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DolColumns:
    case_status: str
    employer_name: str
    job_title: str
    wage_from: str
    wage_unit: str


@dataclass(frozen=True)
class UscisColumns:
    employer: str
    fiscal_year: str
    # new_h1b = fresh/cap sponsorship: New Employment + New Concurrent.
    # Empirically identical to the legacy export's single "Initial" column
    # (FY2020: 122,894 = 121,874 + 1,020, exact).
    # transfers = Change of Employer: worker already on H-1B moving in.
    # Empty transfer tuples = this vintage has no breakout -> transfers NULL.
    new_approval_columns: tuple[str, ...]
    new_denial_columns: tuple[str, ...]
    transfer_approval_columns: tuple[str, ...]
    transfer_denial_columns: tuple[str, ...]


# Modern OFLC disclosure layout (FY2020+)
DOL_FY2020_PLUS = DolColumns(
    case_status="CASE_STATUS",
    employer_name="EMPLOYER_NAME",
    job_title="JOB_TITLE",
    wage_from="WAGE_RATE_OF_PAY_FROM",
    wage_unit="WAGE_UNIT_OF_PAY",
)

# Legacy alias used in some older exports
DOL_LEGACY = DolColumns(
    case_status="STATUS",
    employer_name="LCA_CASE_EMPLOYER_NAME",
    job_title="LCA_CASE_JOB_TITLE",
    wage_from="LCA_CASE_WAGE_RATE_FROM",
    wage_unit="LCA_CASE_WAGE_RATE_UNIT",
)

# Real USCIS H-1B Employer Data Hub export with split petition-type columns.
# Excluded from both categories as same-employer renewals/tweaks:
# Continuation, Change with Same Employer, Amended. (Per the USCIS Data Hub
# glossary Part 2 Q2 petition-type definitions.)
USCIS_DATA_HUB = UscisColumns(
    employer="Employer (Petitioner) Name",
    fiscal_year="Fiscal Year",
    new_approval_columns=(
        "New Employment Approval",
        "New Concurrent Approval",
    ),
    new_denial_columns=(
        "New Employment Denial",
        "New Concurrent Denial",
    ),
    transfer_approval_columns=("Change of Employer Approval",),
    transfer_denial_columns=("Change of Employer Denial",),
)

# Old Data Hub export / synthetic fixture: single pre-summed Initial column
# (= New Employment + New Concurrent). No transfer breakout available.
USCIS_STANDARD = UscisColumns(
    employer="Employer",
    fiscal_year="Fiscal Year",
    new_approval_columns=("Initial Approval",),
    new_denial_columns=("Initial Denial",),
    transfer_approval_columns=(),
    transfer_denial_columns=(),
)

USCIS_LOWER = UscisColumns(
    employer="employer",
    fiscal_year="fiscal_year",
    new_approval_columns=("initial_approval",),
    new_denial_columns=("initial_denial",),
    transfer_approval_columns=(),
    transfer_denial_columns=(),
)


def dol_columns_for_fy(fiscal_year: int) -> DolColumns:
    if fiscal_year >= 2020:
        return DOL_FY2020_PLUS
    return DOL_LEGACY


def resolve_dol_columns(header: tuple[str, ...]) -> DolColumns | None:
    """Pick the map whose employer column exists in the file header."""
    header_set = {h.strip() for h in header}
    for cols in (DOL_FY2020_PLUS, DOL_LEGACY):
        if cols.employer_name in header_set:
            return cols
    return None


def resolve_uscis_columns(header: tuple[str, ...]) -> UscisColumns:
    header_set = {h.strip() for h in header}
    for cols in (USCIS_DATA_HUB, USCIS_STANDARD, USCIS_LOWER):
        if cols.employer in header_set:
            return cols
    return USCIS_LOWER
