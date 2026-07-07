"""ETL tests against synthetic fixtures."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import pytest

from etl.build import YearBucket, build_fixture_database, ingest_uscis_csv
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


def test_uscis_denial_joined(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        """
        SELECT uscis_initial_approvals, uscis_initial_denials
        FROM aggregates WHERE canonical_employer='DATADOG' AND fiscal_year=2025
        """
    ).fetchone()
    assert row[0] == 50
    assert row[1] == 5
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


def _data_hub_row(fy, name, new_app, new_den, concurrent_app, cont_app):
    cells = [
        "1", f"{fy}   ", name, "1234", "54 - Prof", "CITY", "CA", "90001",
        str(new_app), str(new_den), str(cont_app), "0", "0", "0",
        str(concurrent_app), "0", "0", "0", "0", "0",
    ]
    return "\t".join(cells)


def test_uscis_data_hub_real_schema(tmp_path):
    # ACME: 10 new-employment + 3 new-concurrent approvals = 13 initial; 2 denials.
    # Continuation approvals (7) must NOT count toward initial.
    lines = [
        _DATA_HUB_HEADER,
        _data_hub_row(2026, "ACME CORP", new_app=10, new_den=2, concurrent_app=3, cont_app=7),
    ]
    csv_path = tmp_path / "Employer Information.csv"
    # UTF-16 LE with BOM, as USCIS ships it.
    csv_path.write_bytes("\r\n".join(lines).encode("utf-16"))

    buckets: dict = defaultdict(YearBucket)
    ingest_uscis_csv(csv_path, buckets)

    bucket = buckets[("ACME", 2026)]
    assert bucket.initial_approvals == 13  # 10 + 3, not 10 + 3 + 7
    assert bucket.initial_denials == 2
