"""Ship gate: marquee employers must join across DOL and USCIS.

Runs against the real data/h1b_data.db; skipped when absent (CI). Any
failure is a ship blocker per the entity-resolution spec — fix via a
Layer-1 rule (with tests) or a reviewed alias entry, never by weakening
the list without Ishan's sign-off."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl.aliases import load_aliases
from etl.canonicalize import canonicalize

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "h1b_data.db"

pytestmark = pytest.mark.skipif(not REAL_DB.exists(), reason="real build not present")

SPONSORS = [
    # big tech
    "Amazon.com Services LLC", "Google LLC", "Microsoft Corporation",
    "Meta Platforms Inc", "Apple Inc", "NVIDIA Corporation", "Intel Corporation",
    "Oracle America Inc", "Salesforce Inc", "Adobe Inc",
    "International Business Machines Corporation", "Cisco Systems Inc",
    "Qualcomm Technologies Inc", "Uber Technologies Inc", "Intuit Inc",
    # consultancies / IT services
    "Deloitte Consulting LLP", "Ernst & Young U.S. LLP", "Accenture LLP",
    "Infosys Limited", "Tata Consultancy Services Limited", "Wipro Limited",
    "HCL America Inc", "Cognizant Technology Solutions US Corp",
    "Capgemini America Inc", "Tech Mahindra Americas Inc",
    "McKinsey & Company Inc United States",
    # banks / finance
    "JPMorgan Chase & Co", "Goldman Sachs & Co LLC", "Morgan Stanley & Co LLC",
    "Citibank N.A.", "Bank of America N.A.", "Wells Fargo Bank N.A.",
    "Capital One Services LLC",
    # universities / research / health (cap-exempt, high volume)
    "Stanford University", "Massachusetts Institute of Technology",
    "University of Michigan", "Johns Hopkins University", "Columbia University",
    "Mayo Clinic", "Cleveland Clinic",
]


def test_known_sponsors_join():
    aliases = load_aliases()
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    latest = int(
        conn.execute("SELECT value FROM meta WHERE key='latest_complete_fy'").fetchone()[0]
    )
    failures = []
    for name in SPONSORS:
        canon = canonicalize(name)
        canon = aliases.get(canon, canon)
        row = conn.execute(
            "SELECT certified_count, uscis_new_approvals FROM aggregates"
            " WHERE canonical_employer=? AND fiscal_year=?",
            (canon, latest),
        ).fetchone()
        if row is None or row[0] <= 0 or row[1] <= 0:
            failures.append((name, canon, row))
    conn.close()
    assert not failures, "\n".join(f"{n!r} -> {c!r}: {r}" for n, c, r in failures)
