"""Daily quota enforcement — midnight UTC reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.config import DEMO_QUOTA_PER_DAY, KEY_QUOTA_PER_DAY
from app.db import UserDB


@dataclass(frozen=True)
class QuotaResult:
    allowed: bool
    remaining: int
    limit: int
    reset_at: str


def _utc_day(now: datetime | None = None) -> str:
    dt = now or datetime.now(UTC)
    return dt.strftime("%Y-%m-%d")


def _next_midnight_utc(now: datetime | None = None) -> str:
    dt = now or datetime.now(UTC)
    tomorrow = dt.date().toordinal() + 1
    from datetime import date

    reset = datetime.combine(date.fromordinal(tomorrow), datetime.min.time(), tzinfo=UTC)
    return reset.isoformat()


def check_and_increment(
    db: UserDB,
    scope: str,
    scope_key: str,
    limit: int,
) -> QuotaResult:
    day = _utc_day()
    with db.connect() as conn:
        if db._is_sqlite:
            row = conn.execute(
                "SELECT count FROM quota_usage WHERE scope=? AND scope_key=? AND day=?",
                (scope, scope_key, day),
            ).fetchone()
            count = row[0] if row else 0
            if count >= limit:
                return QuotaResult(
                    allowed=False,
                    remaining=0,
                    limit=limit,
                    reset_at=_next_midnight_utc(),
                )
            conn.execute(
                """
                INSERT INTO quota_usage (scope, scope_key, day, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(scope, scope_key, day)
                DO UPDATE SET count = count + 1
                """,
                (scope, scope_key, day),
            )
            new_count = count + 1
        else:
            row = conn.execute(
                """
                SELECT count FROM quota_usage
                WHERE scope=%s AND scope_key=%s AND day=%s
                """,
                (scope, scope_key, day),
            ).fetchone()
            count = row["count"] if row else 0
            if count >= limit:
                return QuotaResult(
                    allowed=False,
                    remaining=0,
                    limit=limit,
                    reset_at=_next_midnight_utc(),
                )
            conn.execute(
                """
                INSERT INTO quota_usage (scope, scope_key, day, count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (scope, scope_key, day)
                DO UPDATE SET count = quota_usage.count + 1
                """,
                (scope, scope_key, day),
            )
            new_count = count + 1

    return QuotaResult(
        allowed=True,
        remaining=max(0, limit - new_count),
        limit=limit,
        reset_at=_next_midnight_utc(),
    )


def check_key_quota(db: UserDB, key_id: int) -> QuotaResult:
    return check_and_increment(db, "key", str(key_id), KEY_QUOTA_PER_DAY)


def check_demo_quota(db: UserDB, client_ip: str) -> QuotaResult:
    return check_and_increment(db, "demo_ip", client_ip, DEMO_QUOTA_PER_DAY)
