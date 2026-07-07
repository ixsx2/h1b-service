"""Optional real-file ETL validation — skipped unless files are present."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl.build import build_from_paths

REAL_DIR = Path(__file__).parent / "fixtures" / "real"


def _real_files():
    dol = sorted(REAL_DIR.glob("LCA_Disclosure_Data_FY*.xlsx"))
    uscis = sorted(REAL_DIR.glob("*.csv"))
    return dol, uscis


@pytest.mark.skipif(
    not _real_files()[0],
    reason="Place FY2025/FY2026 DOL xlsx files in tests/fixtures/real/",
)
def test_real_dol_build(tmp_path):
    dol_files, uscis_files = _real_files()
    out = tmp_path / "h1b_data.db"
    build_from_paths(dol_files, uscis_files, out)
    conn = sqlite3.connect(out)
    count = conn.execute("SELECT count(*) FROM employers").fetchone()[0]
    conn.close()
    assert count > 1000
