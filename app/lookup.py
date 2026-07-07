"""Employer lookup: canonicalize -> exact -> FTS5 fuzzy."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from etl.canonicalize import canonicalize, name_variants

LookupOutcome = Literal["exact", "fuzzy_single", "candidates", "unmatched"]


@dataclass(frozen=True)
class LookupResult:
    outcome: LookupOutcome
    canonical_employer: str | None = None
    matched_as: str | None = None
    candidates: list[str] | None = None


def _exact_match(conn: sqlite3.Connection, query: str) -> str | None:
    canon = canonicalize(query)
    row = conn.execute(
        "SELECT canonical_employer FROM employers WHERE canonical_employer = ?",
        (canon,),
    ).fetchone()
    if row:
        return row[0]

    for variant in name_variants(query):
        row = conn.execute(
            "SELECT canonical_employer FROM filed_names WHERE filed_name = ?",
            (variant.upper(),),
        ).fetchone()
        if row:
            return row[0]
    return None


def _fts_query(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[str]:
    tokens = [t for t in canonicalize(query).split() if len(t) > 1]
    if not tokens:
        return []
    match_expr = " OR ".join(f'"{t}"' for t in tokens)
    rows = conn.execute(
        """
        SELECT DISTINCT canonical_employer
        FROM employer_search
        WHERE employer_search MATCH ?
        LIMIT ?
        """,
        (match_expr, limit),
    ).fetchall()
    return [r[0] for r in rows]


def lookup_employer(conn: sqlite3.Connection, company: str) -> LookupResult:
    company = company.strip()
    if not company:
        return LookupResult(outcome="unmatched")

    exact = _exact_match(conn, company)
    if exact:
        matched_as = None
        canon_query = canonicalize(company)
        if exact != canon_query:
            matched_as = exact
        return LookupResult(outcome="exact", canonical_employer=exact, matched_as=matched_as)

    hits = _fts_query(conn, company)
    if len(hits) == 1:
        return LookupResult(
            outcome="fuzzy_single",
            canonical_employer=hits[0],
            matched_as=hits[0],
        )
    if len(hits) > 1:
        return LookupResult(outcome="candidates", candidates=hits)
    return LookupResult(outcome="unmatched")
