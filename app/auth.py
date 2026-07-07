"""Passwordless OTP auth and API key management."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app import config
from app.config import (
    OTP_EXPIRY_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_RATE_PER_HOUR,
    OTP_SECRET,
)
from app.db import UserDB
from app.email import send_otp_email


@dataclass(frozen=True)
class AuthError:
    error: str
    hint: str


def _hash(value: str) -> str:
    return hashlib.sha256(f"{OTP_SECRET}:{value}".encode()).hexdigest()


def _hour_bucket(now: datetime | None = None) -> str:
    dt = now or datetime.now(UTC)
    return dt.strftime("%Y-%m-%dT%H")


def _utc_day(now: datetime | None = None) -> str:
    dt = now or datetime.now(UTC)
    return dt.strftime("%Y-%m-%d")


def _check_otp_rate(db: UserDB, scope: str, scope_key: str) -> AuthError | None:
    if config.TESTING:
        return None
    bucket = _hour_bucket()
    with db.connect() as conn:
        if db._is_sqlite:
            row = conn.execute(
                "SELECT count FROM otp_rate WHERE scope=? AND scope_key=? AND hour_bucket=?",
                (scope, scope_key, bucket),
            ).fetchone()
            count = row[0] if row else 0
            if count >= OTP_RATE_PER_HOUR:
                return AuthError(
                    error="rate_limited",
                    hint="Too many code requests. Try again in an hour.",
                )
            conn.execute(
                """
                INSERT INTO otp_rate (scope, scope_key, hour_bucket, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(scope, scope_key, hour_bucket)
                DO UPDATE SET count = count + 1
                """,
                (scope, scope_key, bucket),
            )
        else:
            row = conn.execute(
                """
                SELECT count FROM otp_rate
                WHERE scope=%s AND scope_key=%s AND hour_bucket=%s
                """,
                (scope, scope_key, bucket),
            ).fetchone()
            count = row["count"] if row else 0
            if count >= OTP_RATE_PER_HOUR:
                return AuthError(
                    error="rate_limited",
                    hint="Too many code requests. Try again in an hour.",
                )
            conn.execute(
                """
                INSERT INTO otp_rate (scope, scope_key, hour_bucket, count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (scope, scope_key, hour_bucket)
                DO UPDATE SET count = otp_rate.count + 1
                """,
                (scope, scope_key, bucket),
            )
    return None


def request_otp(db: UserDB, email: str, client_ip: str) -> AuthError | None:
    email = email.strip().lower()
    if not email or "@" not in email:
        return AuthError(error="invalid_email", hint="Provide a valid email address.")

    for scope, key in (("email", email), ("ip", client_ip)):
        err = _check_otp_rate(db, scope, key)
        if err:
            return err

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = datetime.now(UTC) + timedelta(seconds=OTP_EXPIRY_SECONDS)
    now = datetime.now(UTC).isoformat()

    with db.connect() as conn:
        if db._is_sqlite:
            conn.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
            conn.execute(
                """
                INSERT INTO otp_codes (email, code_hash, expires_at, attempts, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (email, _hash(code), expires.isoformat(), now),
            )
        else:
            conn.execute("DELETE FROM otp_codes WHERE email = %s", (email,))
            conn.execute(
                """
                INSERT INTO otp_codes (email, code_hash, expires_at, attempts, created_at)
                VALUES (%s, %s, %s, 0, %s)
                """,
                (email, _hash(code), expires, now),
            )

    send_otp_email(email, code)
    return None


def verify_otp(db: UserDB, email: str, code: str) -> tuple[str | None, AuthError | None]:
    email = email.strip().lower()
    code = code.strip()
    if not email or not code:
        return None, AuthError(error="invalid_request", hint="Email and code are required.")

    with db.connect() as conn:
        if db._is_sqlite:
            row = conn.execute(
                "SELECT id, code_hash, expires_at, attempts FROM otp_codes WHERE email = ?",
                (email,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, code_hash, expires_at, attempts FROM otp_codes WHERE email = %s",
                (email,),
            ).fetchone()

        if not row:
            return None, AuthError(error="no_code", hint="Request a code first.")

        if db._is_sqlite:
            attempts = row["attempts"]
            expires_raw = row["expires_at"]
            code_hash = row["code_hash"]
            otp_id = row["id"]
        else:
            attempts = row["attempts"]
            expires_raw = row["expires_at"]
            code_hash = row["code_hash"]
            otp_id = row["id"]

        if attempts >= OTP_MAX_ATTEMPTS:
            return None, AuthError(error="too_many_attempts", hint="Request a new code.")

        expires_raw = expires_raw
        expires = (
            datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
            if isinstance(expires_raw, str)
            else expires_raw
        )
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires:
            return None, AuthError(error="expired", hint="Code expired. Request a new one.")

        if not hmac.compare_digest(code_hash, _hash(code)):
            new_attempts = attempts + 1
            if db._is_sqlite:
                conn.execute(
                    "UPDATE otp_codes SET attempts = ? WHERE id = ?",
                    (new_attempts, otp_id),
                )
            else:
                conn.execute(
                    "UPDATE otp_codes SET attempts = %s WHERE id = %s",
                    (new_attempts, otp_id),
                )
            return None, AuthError(error="invalid_code", hint="Wrong code. Try again.")

        if db._is_sqlite:
            conn.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
        else:
            conn.execute("DELETE FROM otp_codes WHERE email = %s", (email,))

    api_key = _issue_api_key(db, email)
    return api_key, None


def _issue_api_key(db: UserDB, email: str) -> str:
    raw_key = secrets.token_urlsafe(32)
    key_hash = _hash(raw_key)
    now = datetime.now(UTC).isoformat()

    with db.connect() as conn:
        if db._is_sqlite:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                user_id = row[0]
            else:
                cur = conn.execute(
                    "INSERT INTO users (email, created_at) VALUES (?, ?)",
                    (email, now),
                )
                user_id = cur.lastrowid
            conn.execute(
                "INSERT INTO api_keys (user_id, key_hash, created_at) VALUES (?, ?, ?)",
                (user_id, key_hash, now),
            )
        else:
            row = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
            if row:
                user_id = row["id"]
            else:
                user_id = conn.execute(
                    "INSERT INTO users (email) VALUES (%s) RETURNING id",
                    (email,),
                ).fetchone()["id"]
            conn.execute(
                "INSERT INTO api_keys (user_id, key_hash) VALUES (%s, %s)",
                (user_id, key_hash),
            )
    return raw_key


def resolve_api_key(db: UserDB, raw_key: str) -> int | None:
    key_hash = _hash(raw_key)
    with db.connect() as conn:
        if db._is_sqlite:
            row = conn.execute(
                "SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()
            return row[0] if row else None
        row = conn.execute(
            "SELECT id FROM api_keys WHERE key_hash = %s", (key_hash,)
        ).fetchone()
        return row["id"] if row else None
