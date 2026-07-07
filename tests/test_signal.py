"""Table-driven signal tier, trend, and denial rate tests."""

from __future__ import annotations

import pytest

from app.signal import (
    build_signal,
    compute_denial_rate,
    compute_tier,
    compute_trend,
)

TIER_CASES = [
    pytest.param(
        {2025: 25, 2024: 10, 2023: 5, 2022: 0, 2021: 0},
        2025,
        "ACTIVE",
        id="active-latest-20plus",
    ),
    pytest.param(
        {2025: 10, 2024: 8, 2023: 8, 2022: 0, 2021: 0},
        2025,
        "ESTABLISHED",
        id="established-3yr-20plus",
    ),
    pytest.param(
        {2025: 2, 2024: 1, 2023: 0, 2022: 0, 2021: 0},
        2025,
        "RARE",
        id="rare-some-history",
    ),
    pytest.param(
        {2025: 0, 2024: 0, 2023: 0, 2022: 0, 2021: 0},
        2025,
        "NONE",
        id="none-zero-window",
    ),
]


@pytest.mark.parametrize("counts,latest_fy,expected", TIER_CASES)
def test_compute_tier(counts, latest_fy, expected):
    assert compute_tier(counts, latest_fy) == expected


TREND_CASES = [
    pytest.param({2025: 20, 2024: 10}, 2025, "rising", id="rising"),
    pytest.param({2025: 5, 2024: 15}, 2025, "falling", id="falling"),
    pytest.param({2025: 12, 2024: 12}, 2025, "flat", id="flat"),
    pytest.param({2025: 3, 2024: 4}, 2025, None, id="null-low-volume"),
]


@pytest.mark.parametrize("counts,latest_fy,expected", TREND_CASES)
def test_compute_trend(counts, latest_fy, expected):
    assert compute_trend(counts, latest_fy) == expected


DENIAL_CASES = [
    pytest.param(50, 5, 0.0909, False, id="normal-rate"),
    pytest.param(10, 5, 0.3333, True, id="caution-high-rate"),
    pytest.param(5, 1, None, False, id="null-small-denominator"),
]


@pytest.mark.parametrize("app,den,rate,caution", DENIAL_CASES)
def test_compute_denial_rate(app, den, rate, caution):
    result_rate, result_caution = compute_denial_rate(app, den)
    if rate is None:
        assert result_rate is None
    else:
        assert result_rate == pytest.approx(rate, rel=1e-3)
    assert result_caution is caution


def test_build_signal_integration():
    rows = [
        {
            "fiscal_year": 2025,
            "certified_count": 25,
            "uscis_initial_approvals": 50,
            "uscis_initial_denials": 5,
        },
        {
            "fiscal_year": 2024,
            "certified_count": 15,
            "uscis_initial_approvals": 0,
            "uscis_initial_denials": 0,
        },
    ]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.tier == "ACTIVE"
    assert signal.trend == "rising"
    assert signal.denial_rate == pytest.approx(0.0909, rel=1e-3)
