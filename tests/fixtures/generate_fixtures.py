"""Generate synthetic DOL xlsx + USCIS csv fixtures for tests."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

FIXTURES = Path(__file__).parent

DOL_ROWS = [
    # FY2025 — DATADOG ACTIVE (25 certified)
    *[
        ("CERTIFIED", "Datadog, Inc.", "Software Engineer", 150000, "Year")
        for _ in range(25)
    ],
    *[
        ("CERTIFIED", "DATADOG INC", "Site Reliability Engineer", 160000, "Year")
        for _ in range(5)
    ],
    # ESTAB CORP — established pattern
    *[
        ("CERTIFIED", "Estab Corp LLC", "Data Engineer", 120000, "Year")
        for _ in range(10)
    ],
    *[
        ("DENIED", "Estab Corp LLC", "Data Engineer", 120000, "Year")
        for _ in range(2)
    ],
    # RARE — few filings
    ("CERTIFIED", "Rare Startup Inc", "Engineer", 100000, "Year"),
    ("CERTIFIED", "Rare Startup Inc", "Engineer", 105000, "Year"),
    # Withdrawn — should not count
    ("WITHDRAWN", "Datadog, Inc.", "Intern", 50000, "Year"),
]

DOL_PRIOR = [
    # FY2024 — ESTAB prior years + DATADOG trend
    *[
        ("CERTIFIED", "Estab Corp LLC", "Data Engineer", 115000, "Year")
        for _ in range(8)
    ],
    *[
        ("CERTIFIED", "DATADOG INC", "Software Engineer", 140000, "Year")
        for _ in range(15)
    ],
    ("CERTIFIED", "Rare Startup Inc", "Engineer", 95000, "Year"),
]

USCIS_ROWS = [
    "Employer,Fiscal Year,Initial Approval,Initial Denial",
    "DATADOG,2025,50,5",
    "ESTAB,2025,8,2",
    "RARE STARTUP,2025,1,0",
]


def write_dol(path: Path, rows: list[tuple]) -> None:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    ws.append(
        [
            "CASE_NUMBER",
            "CASE_STATUS",
            "EMPLOYER_NAME",
            "JOB_TITLE",
            "WAGE_RATE_OF_PAY_FROM",
            "WAGE_UNIT_OF_PAY",
        ]
    )
    for i, row in enumerate(rows):
        ws.append([f"CASE-{i}", *row])
    wb.save(path)


def main() -> None:
    write_dol(FIXTURES / "dol_FY2025_Q4.xlsx", DOL_ROWS)
    write_dol(FIXTURES / "dol_FY2024_Q4.xlsx", DOL_PRIOR)
    (FIXTURES / "uscis_fy2025.csv").write_text("\n".join(USCIS_ROWS) + "\n", encoding="utf-8")
    print("Wrote fixtures to", FIXTURES)


if __name__ == "__main__":
    main()
