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
    # "Initial" approvals/denials are summed across these petition-type columns.
    # The synthetic fixture ships single pre-summed columns; the real Data Hub
    # export splits them by petition type (New Employment, New Concurrent, ...).
    approval_columns: tuple[str, ...]
    denial_columns: tuple[str, ...]


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

# Real USCIS H-1B Employer Data Hub annual export (UTF-16 LE, tab-delimited).
# "Initial" = first-time petitions: New Employment + New Concurrent, matching
# USCIS's own "Initial Approval/Denial" definition. Continuation, Change, and
# Amended petitions are excluded (they are not new sponsorships).
USCIS_DATA_HUB = UscisColumns(
    employer="Employer (Petitioner) Name",
    fiscal_year="Fiscal Year",
    approval_columns=("New Employment Approval", "New Concurrent Approval"),
    denial_columns=("New Employment Denial", "New Concurrent Denial"),
)

# Synthetic fixture layout: single pre-summed columns.
USCIS_STANDARD = UscisColumns(
    employer="Employer",
    fiscal_year="Fiscal Year",
    approval_columns=("Initial Approval",),
    denial_columns=("Initial Denial",),
)

USCIS_LOWER = UscisColumns(
    employer="employer",
    fiscal_year="fiscal_year",
    approval_columns=("initial_approval",),
    denial_columns=("initial_denial",),
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
