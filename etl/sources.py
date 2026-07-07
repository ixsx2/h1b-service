"""Public data source URLs and fiscal-year helpers."""

from __future__ import annotations

from datetime import date

DOL_PERFORMANCE_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
USCIS_DATA_HUB_PAGE = (
    "https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub"
)
USCIS_DATA_HUB_FILES = (
    "https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub/"
    "h-1b-employer-data-hub-files"
)


def fiscal_year_in_progress(today: date | None = None) -> int:
    """Federal FY number for the FY currently in progress."""
    d = today or date.today()
    return d.year + 1 if d.month >= 10 else d.year


def latest_complete_fiscal_year(today: date | None = None) -> int:
    return fiscal_year_in_progress(today) - 1


def last_n_complete_fiscal_years(n: int = 5, today: date | None = None) -> list[int]:
    latest = latest_complete_fiscal_year(today)
    return [latest - i for i in range(n - 1, -1, -1)]


def fiscal_year_from_dol_filename(name: str) -> int | None:
    """Extract FY from names like LCA_Disclosure_Data_FY2025_Q4.xlsx."""
    upper = name.upper()
    marker = "FY"
    idx = upper.find(marker)
    if idx < 0:
        return None
    digits = ""
    for ch in upper[idx + len(marker) :]:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else None
