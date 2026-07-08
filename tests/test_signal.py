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


def _row(fy, certified, new_app=0, new_den=0, tr_app=None, tr_den=None):
    return {
        "fiscal_year": fy,
        "certified_count": certified,
        "uscis_new_approvals": new_app,
        "uscis_new_denials": new_den,
        "uscis_transfer_approvals": tr_app,
        "uscis_transfer_denials": tr_den,
    }


def test_build_signal_split_blocks():
    rows = [
        _row(2025, 25, new_app=50, new_den=5, tr_app=30, tr_den=10),
        _row(2024, 15),
    ]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.tier == "ACTIVE"
    assert signal.trend == "rising"
    assert signal.new_h1b.approvals == 50
    assert signal.new_h1b.denial_rate == pytest.approx(0.0909, rel=1e-3)
    assert signal.new_h1b.caution is False
    assert signal.transfers is not None
    assert signal.transfers.denial_rate == pytest.approx(0.25, rel=1e-3)
    assert signal.transfers.caution is True


def test_build_signal_thresholds_independent_per_block():
    # 8 fresh decisions (below DENIAL_MIN_PETITIONS) but 40 transfer decisions
    rows = [_row(2025, 25, new_app=6, new_den=2, tr_app=38, tr_den=2)]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.denial_rate is None
    assert signal.new_h1b.caution is False
    assert signal.transfers.denial_rate == pytest.approx(0.05, rel=1e-3)


def test_build_signal_transfers_null_when_no_breakout():
    rows = [_row(2025, 25, new_app=50, new_den=5)]  # tr_* stay None
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.approvals == 50
    assert signal.transfers is None


def test_build_signal_no_uscis_row_for_latest_fy():
    # Employer has LCA history but no aggregates row in latest_complete_fy:
    # zero-count blocks, not a null transfers block.
    rows = [_row(2024, 30, new_app=10, new_den=0, tr_app=5, tr_den=0)]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.approvals == 0
    assert signal.new_h1b.denial_rate is None
    assert signal.transfers is not None
    assert signal.transfers.approvals == 0
