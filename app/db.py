"""Database access: read-only aggregates SQLite + user-data store."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL, H1B_DATA_DB


class AggregatesDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or H1B_DATA_DB

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def latest_complete_fy(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'latest_complete_fy'"
            ).fetchone()
            if row:
                return int(row[0])
        from etl.sources import latest_complete_fiscal_year

        return latest_complete_fiscal_year()

    def employer_aggregates(self, canonical: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT fiscal_year, certified_count, salary_median, salary_min,
                       salary_max, top_titles, uscis_initial_approvals,
                       uscis_initial_denials
                FROM aggregates
                WHERE canonical_employer = ?
                ORDER BY fiscal_year
                """,
                (canonical,),
            ).fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "fiscal_year": r["fiscal_year"],
                    "certified_count": r["certified_count"],
                    "salary_median": r["salary_median"],
                    "salary_min": r["salary_min"],
                    "salary_max": r["salary_max"],
                    "top_titles": json.loads(r["top_titles"]),
                    "uscis_initial_approvals": r["uscis_initial_approvals"],
                    "uscis_initial_denials": r["uscis_initial_denials"],
                }
            )
        return result


class UserDB:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or DATABASE_URL
        self._is_sqlite = self.url.startswith("sqlite:")

    def init_schema(self) -> None:
        if self._is_sqlite:
            self._init_sqlite()
        else:
            self._init_postgres()

    def _sqlite_path(self) -> Path:
        parsed = urlparse(self.url)
        return Path(parsed.path.lstrip("/"))

    def _init_sqlite(self) -> None:
        path = self._sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                key_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_rate (
                scope TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                hour_bucket TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (scope, scope_key, hour_bucket)
            );
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                query TEXT,
                key_id INTEGER,
                user_agent TEXT,
                client_ip TEXT
            );
            CREATE TABLE IF NOT EXISTS quota_usage (
                scope TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (scope, scope_key, day)
            );
            """
        )
        conn.commit()
        conn.close()

    def _init_postgres(self) -> None:
        with psycopg.connect(self.url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    key_hash TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS otp_codes (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS otp_rate (
                    scope TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    hour_bucket TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scope, scope_key, hour_bucket)
                );
                CREATE TABLE IF NOT EXISTS request_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
                    endpoint TEXT NOT NULL,
                    query TEXT,
                    key_id INTEGER,
                    user_agent TEXT,
                    client_ip TEXT
                );
                CREATE TABLE IF NOT EXISTS quota_usage (
                    scope TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scope, scope_key, day)
                );
                """
            )
            conn.commit()

    @contextmanager
    def connect(self):
        if self._is_sqlite:
            conn = sqlite3.connect(self._sqlite_path())
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        else:
            with psycopg.connect(self.url, row_factory=dict_row) as conn:
                yield conn
                conn.commit()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)

    def log_request(
        self,
        endpoint: str,
        query: str | None,
        key_id: int | None,
        user_agent: str | None,
        client_ip: str | None,
    ) -> None:
        now = self.utc_now().isoformat()
        with self.connect() as conn:
            if self._is_sqlite:
                conn.execute(
                    """
                    INSERT INTO request_log (
                        timestamp, endpoint, query, key_id, user_agent, client_ip
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (now, endpoint, query, key_id, user_agent, client_ip),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO request_log (endpoint, query, key_id, user_agent, client_ip)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (endpoint, query, key_id, user_agent, client_ip),
                )
