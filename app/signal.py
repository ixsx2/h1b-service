"""Sponsorship Signal: tier, trend, denial rate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from etl.sources import last_n_complete_fiscal_years

SignalTier = Literal["ACTIVE", "ESTABLISHED", "RARE", "NONE"]
Trend = Literal["rising", "falling", "flat"] | None

ACTIVE_THRESHOLD = 20
ESTABLISHED_WINDOW = 3
TREND_MIN_VOLUME = 10
DENIAL_MIN_PETITIONS = 10
DENIAL_CAUTION_RATE = 0.15


@dataclass(frozen=True)
class FiscalYearCount:
    fiscal_year: int
    certified: int


@dataclass(frozen=True)
class SignalResult:
    tier: SignalTier
    trend: Trend
    denial_rate: float | None
    denial_caution: bool
    certified_by_year: list[FiscalYearCount]
    latest_complete_fy: int


def compute_tier(counts_by_fy: dict[int, int], latest_complete_fy: int) -> SignalTier:
    window = last_n_complete_fiscal_years(5)
    total_in_window = sum(counts_by_fy.get(fy, 0) for fy in window)
    if total_in_window == 0:
        return "NONE"

    latest_count = counts_by_fy.get(latest_complete_fy, 0)
    if latest_count >= ACTIVE_THRESHOLD:
        return "ACTIVE"

    last_three = [latest_complete_fy - i for i in range(ESTABLISHED_WINDOW)]
    three_year_total = sum(counts_by_fy.get(fy, 0) for fy in last_three)
    if three_year_total >= ACTIVE_THRESHOLD:
        return "ESTABLISHED"

    return "RARE"


def compute_trend(counts_by_fy: dict[int, int], latest_complete_fy: int) -> Trend:
    prior_fy = latest_complete_fy - 1
    latest = counts_by_fy.get(latest_complete_fy, 0)
    prior = counts_by_fy.get(prior_fy, 0)
    if latest < TREND_MIN_VOLUME and prior < TREND_MIN_VOLUME:
        return None
    if latest > prior:
        return "rising"
    if latest < prior:
        return "falling"
    return "flat"


def compute_denial_rate(approvals: int, denials: int) -> tuple[float | None, bool]:
    decisions = approvals + denials
    if decisions < DENIAL_MIN_PETITIONS:
        return None, False
    rate = denials / decisions
    caution = rate >= DENIAL_CAUTION_RATE
    return round(rate, 4), caution


def build_signal(
    rows: list[dict],
    latest_complete_fy: int | None = None,
) -> SignalResult:
    """rows: aggregate dicts with fiscal_year, certified_count, uscis_* fields."""
    lcfy = latest_complete_fy or last_n_complete_fiscal_years(1)[0]
    counts = {int(r["fiscal_year"]): int(r["certified_count"]) for r in rows}
    tier = compute_tier(counts, lcfy)
    trend = compute_trend(counts, lcfy)

    latest_row = next((r for r in rows if int(r["fiscal_year"]) == lcfy), None)
    approvals = int(latest_row["uscis_initial_approvals"]) if latest_row else 0
    denials = int(latest_row["uscis_initial_denials"]) if latest_row else 0
    denial_rate, denial_caution = compute_denial_rate(approvals, denials)

    window = last_n_complete_fiscal_years(5)
    certified_by_year = [
        FiscalYearCount(fiscal_year=year, certified=counts.get(year, 0)) for year in window
    ]

    return SignalResult(
        tier=tier,
        trend=trend,
        denial_rate=denial_rate,
        denial_caution=denial_caution,
        certified_by_year=certified_by_year,
        latest_complete_fy=lcfy,
    )
