"""Offline tests for pro-rata trim sizing math. No network. No live path."""

from __future__ import annotations

from math import isclose

from alexrag.agents.notional_trim import (
    NOTIONAL_BREACH_POLICY,
    ProRataTrimPlan,
    pro_rata_trim_for_new_entry,
)
from alexrag.config import load_settings


def _close(a: float, b: float) -> bool:
    return isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def test_policy_locked_in_config() -> None:
    settings = load_settings()
    assert settings.hard_limits.notional_breach_policy == NOTIONAL_BREACH_POLICY
    assert settings.hard_limits.max_notional_pct == 1.5
    assert settings.hard_limits.max_positions == 15
    assert settings.hard_limits.max_daily_loss_pct == 0.10
    assert settings.hard_limits.max_portfolio_dd == 0.25
    snap = settings.hard_limits_snapshot()
    assert snap["notional_breach_policy"] == "pro_rata_trim_for_new_entry"


def test_no_trim_when_gross_stays_under_cap() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 50_000.0), ("MSFT", 50_000.0)],
        40_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert plan.policy == "pro_rata_trim_for_new_entry"
    assert plan.overflow == 0.0
    assert plan.trimmed is False
    assert plan.scale_existing == 1.0
    assert plan.entered_notional == 40_000.0
    assert plan.new_clipped_to_cap is False
    assert _close(plan.resulting_gross, 140_000.0)
    assert plan.resulting_gross <= plan.max_gross_notional


def test_pro_rata_trim_makes_room_then_enters_full_new_size() -> None:
    # current 120k + new 50k = 170k > 150k cap → overflow 20k.
    # target existing = 150k - 50k = 100k; scale = 100/120.
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 80_000.0), ("MSFT", 40_000.0)],
        50_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert plan.trimmed is True
    assert plan.new_clipped_to_cap is False
    assert plan.entered_notional == 50_000.0
    assert _close(plan.overflow, 20_000.0)
    assert _close(plan.scale_existing, 100.0 / 120.0)
    assert _close(plan.positions[0].notional_after, 80_000.0 * 100.0 / 120.0)
    assert _close(plan.positions[1].notional_after, 40_000.0 * 100.0 / 120.0)
    assert _close(plan.resulting_gross, 150_000.0)
    assert _close(sum(p.notional_after for p in plan.positions), 100_000.0)


def test_at_cap_trim_existing_to_make_room() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 90_000.0), ("MSFT", 60_000.0)],
        30_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert _close(plan.scale_existing, 0.8)
    assert _close(plan.positions[0].notional_after, 72_000.0)
    assert _close(plan.positions[1].notional_after, 48_000.0)
    assert plan.entered_notional == 30_000.0
    assert _close(plan.resulting_gross, 150_000.0)


def test_empty_book_enters_without_trim() -> None:
    plan = pro_rata_trim_for_new_entry([], 40_000.0, equity=100_000.0, max_notional_pct=1.5)
    assert plan.positions == ()
    assert plan.trimmed is False
    assert plan.entered_notional == 40_000.0
    assert _close(plan.resulting_gross, 40_000.0)


def test_new_entry_alone_above_cap_flattens_book_and_clips_new() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 10_000.0)],
        160_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert plan.new_clipped_to_cap is True
    assert plan.entered_notional == 150_000.0
    assert _close(plan.scale_existing, 0.0)
    assert _close(plan.positions[0].notional_after, 0.0)
    assert _close(plan.resulting_gross, 150_000.0)


def test_residual_lands_on_last_position() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("A", 10.0), ("B", 20.0), ("C", 31.0)],
        100.0,
        equity=100.0,
        max_notional_pct=1.5,
    )
    target_existing = 50.0
    assert _close(sum(abs(p.notional_after) for p in plan.positions), target_existing)
    assert _close(plan.positions[0].notional_after, 10.0 * (50.0 / 61.0))
    assert _close(plan.positions[1].notional_after, 20.0 * (50.0 / 61.0))
    leftover = target_existing - (
        plan.positions[0].notional_after + plan.positions[1].notional_after
    )
    assert _close(plan.positions[2].notional_after, leftover)
    assert _close(plan.resulting_gross, 150.0)
    assert plan.entered_notional == 100.0


def test_shorts_count_as_gross_and_keep_sign() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 80_000.0), ("TSLA", -40_000.0)],
        50_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert _close(plan.current_gross, 120_000.0)
    assert plan.positions[1].notional_before == -40_000.0
    assert plan.positions[1].notional_after < 0
    assert _close(abs(plan.positions[1].notional_after), 40_000.0 * 100.0 / 120.0)
    assert _close(plan.resulting_gross, 150_000.0)


def test_equity_zero_fail_closed_does_not_enter() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 10_000.0)],
        5_000.0,
        equity=0.0,
        max_notional_pct=1.5,
    )
    assert plan.ready is False
    assert plan.entered_notional == 0.0
    assert plan.positions[0].notional_after == 10_000.0
    assert isinstance(plan, ProRataTrimPlan)


def test_negative_new_notional_treated_as_zero() -> None:
    plan = pro_rata_trim_for_new_entry(
        [("AAPL", 10_000.0)],
        -5_000.0,
        equity=100_000.0,
        max_notional_pct=1.5,
    )
    assert plan.entered_notional == 0.0
    assert plan.trimmed is False
    assert plan.positions[0].notional_after == 10_000.0
