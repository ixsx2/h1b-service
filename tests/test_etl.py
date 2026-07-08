"""ETL tests against synthetic fixtures."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import pytest

from etl.build import YearBucket, build_fixture_database, ingest_uscis_csv, ingest_uscis_xlsx
from etl.canonicalize import canonicalize

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def built(tmp_path):
    gen = FIXTURES / "generate_fixtures.py"
    if gen.exists():
        import subprocess
        import sys

        subprocess.run([sys.executable, str(gen)], check=True)
    out = tmp_path / "h1b_data.db"
    build_fixture_database(FIXTURES, out)
    return out


def test_canonicalize_suffix_stripping():
    assert canonicalize("Datadog, Inc.") == "DATADOG"
    # "N.V." dots removed → "NV", then NV suffix stripped
    assert canonicalize("N.V. Energy Corp.") == "ENERGY"


def test_build_creates_employers(built):
    conn = sqlite3.connect(built)
    employers = {r[0] for r in conn.execute("SELECT canonical_employer FROM employers")}
    assert "DATADOG" in employers
    assert "ESTAB" in employers
    conn.close()


def test_datadog_active_counts(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        """
        SELECT certified_count FROM aggregates
        WHERE canonical_employer='DATADOG' AND fiscal_year=2025
        """
    ).fetchone()
    assert row is not None
    assert row[0] >= 20
    conn.close()


def test_filed_name_mapping(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        "SELECT canonical_employer FROM filed_names WHERE filed_name LIKE '%DATADOG%'"
    ).fetchone()
    assert row[0] == "DATADOG"
    conn.close()


def test_uscis_split_columns_joined(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        """
        SELECT uscis_new_approvals, uscis_new_denials,
               uscis_transfer_approvals, uscis_transfer_denials
        FROM aggregates WHERE canonical_employer='DATADOG' AND fiscal_year=2025
        """
    ).fetchone()
    # Fixture CSV is legacy pre-summed: new gets the Initial numbers,
    # transfers stay NULL (breakout unavailable), never 0.
    assert row[0] == 50
    assert row[1] == 5
    assert row[2] is None
    assert row[3] is None
    conn.close()


# Real USCIS H-1B Employer Data Hub export shape: UTF-16 LE, tab-delimited,
# trailing whitespace in the 'Fiscal Year   ' header, and split petition-type
# columns rather than a single 'Initial Approval'. This mirror keeps the ingest
# from silently regressing to the synthetic fixture shape (see column_maps).
_DATA_HUB_HEADER = (
    "Line by line\tFiscal Year   \tEmployer (Petitioner) Name\tTax ID\t"
    "Industry (NAICS) Code\tPetitioner City\tPetitioner State\tPetitioner Zip Code\t"
    "New Employment Approval\tNew Employment Denial\tContinuation Approval\t"
    "Continuation Denial\tChange with Same Employer Approval\t"
    "Change with Same Employer Denial\tNew Concurrent Approval\tNew Concurrent Denial\t"
    "Change of Employer Approval\tChange of Employer Denial\tAmended Approval\tAmended Denial"
)


def _data_hub_row(fy, name, new_app, new_den, concurrent_app, cont_app, change_emp_app=0):
    # Column order must match _DATA_HUB_HEADER exactly.
    cells = [
        "1", f"{fy}   ", name, "1234", "54 - Prof", "CITY", "CA", "90001",
        str(new_app), str(new_den),        # New Employment
        str(cont_app), "0",                # Continuation
        "0", "0",                          # Change with Same Employer
        str(concurrent_app), "0",          # New Concurrent
        str(change_emp_app), "0",          # Change of Employer
        "0", "0",                          # Amended
    ]
    return "\t".join(cells)


def test_uscis_column_maps_split_new_vs_transfer():
    from etl.column_maps import USCIS_DATA_HUB, USCIS_STANDARD

    # new_h1b = fresh/cap only; Change of Employer must NOT be in the new tuples
    assert USCIS_DATA_HUB.new_approval_columns == (
        "New Employment Approval",
        "New Concurrent Approval",
    )
    assert USCIS_DATA_HUB.transfer_approval_columns == ("Change of Employer Approval",)
    assert USCIS_DATA_HUB.transfer_denial_columns == ("Change of Employer Denial",)
    # Legacy pre-summed export has no breakout
    assert USCIS_STANDARD.new_approval_columns == ("Initial Approval",)
    assert USCIS_STANDARD.transfer_approval_columns == ()


def test_uscis_data_hub_real_schema(tmp_path):
    # new_h1b = New Employment + New Concurrent (fresh/cap); Change of Employer
    # is a transfer, tracked separately. Continuation (7) counts in neither.
    lines = [
        _DATA_HUB_HEADER,
        _data_hub_row(
            2026, "ACME CORP",
            new_app=10, new_den=2, concurrent_app=3, cont_app=7, change_emp_app=5,
        ),
    ]
    csv_path = tmp_path / "Employer Information.csv"
    # UTF-16 LE with BOM, as USCIS ships it.
    csv_path.write_bytes("\r\n".join(lines).encode("utf-16"))

    buckets: dict = defaultdict(YearBucket)
    ingest_uscis_csv(csv_path, buckets)

    bucket = buckets[("ACME", 2026)]
    # new_h1b = 10 New Employment + 3 New Concurrent; NOT continuation (7), NOT COE
    assert bucket.new_approvals == 13
    assert bucket.new_denials == 2
    # transfers = Change of Employer only
    assert bucket.transfer_approvals == 5
    assert bucket.transfer_denials == 0


def test_uscis_xlsx_ingest_multirow_summation(tmp_path):
    # Real consolidated files: one employer = many rows (per NAICS/city/ZIP),
    # numbers may be ints or comma-formatted strings.
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    ws.append([h for h in _DATA_HUB_HEADER.split("\t")])
    base = ["1", 2025, "ACME CORP", "1234", "54 - Prof", "CITY", "CA", "90001"]
    #                 NewEmpA NewEmpD ContA ContD SameA SameD ConcA ConcD COEA COED AmA AmD
    ws.append(base + [10, 1, 7, 0, 0, 0, 2, 0, 4, 1, 0, 0])
    ws.append(base + ["1,000", 0, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0])
    # blank employer name: data-entry error, skipped
    ws.append(["2", 2025, "", "9999", "54", "X", "CA", "0", 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    path = tmp_path / "Employer Information_test.xlsx"
    wb.save(path)

    buckets: dict = defaultdict(YearBucket)
    filed: dict = defaultdict(set)
    ingest_uscis_xlsx(path, buckets, filed)

    bucket = buckets[("ACME", 2025)]
    assert bucket.new_approvals == 1012  # 10 + 2 + 1,000
    assert bucket.new_denials == 1
    assert bucket.transfer_approvals == 10  # 4 + 6
    assert bucket.transfer_denials == 1
    assert "ACME CORP" in filed


def test_uscis_legacy_schema_has_no_transfer_breakout(tmp_path):
    lines = [
        "Employer,Fiscal Year,Initial Approval,Initial Denial",
        "ACME CORP,2025,40,4",
    ]
    csv_path = tmp_path / "uscis_legacy.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    buckets: dict = defaultdict(YearBucket)
    ingest_uscis_csv(csv_path, buckets)

    bucket = buckets[("ACME", 2025)]
    assert bucket.new_approvals == 40
    assert bucket.new_denials == 4
    # NULL, not 0: this vintage cannot say
    assert bucket.transfer_approvals is None
    assert bucket.transfer_denials is None
