"""ETL tests against synthetic fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl.build import build_fixture_database
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
