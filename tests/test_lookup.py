"""Table-driven employer lookup tests."""

from __future__ import annotations

import sqlite3

import pytest

from app.lookup import lookup_employer

LOOKUP_CASES = [
    pytest.param("Datadog, Inc.", "exact", "DATADOG", id="filed-name-exact"),
    pytest.param("DATADOG", "exact", "DATADOG", id="canonical-exact"),
    pytest.param("ZZZ UNKNOWN CORP", "unmatched", None, id="no-match"),
]


@pytest.fixture
def lookup_conn(built_db):
    conn = sqlite3.connect(built_db)
    yield conn
    conn.close()


@pytest.mark.parametrize("query,outcome,canonical", LOOKUP_CASES)
def test_lookup_outcomes(lookup_conn, query, outcome, canonical):
    result = lookup_employer(lookup_conn, query)
    assert result.outcome == outcome
    if canonical:
        assert result.canonical_employer == canonical
