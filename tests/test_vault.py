from datetime import datetime

import pytest

from goldvault import config as C
from goldvault.vault import (
    Vault, apply_weekly_hedge_expiry, cvar_from_buckets, hedge_mark_to_market, init_vault,
    initial_target_price, monday_of_week, resolve_event_with_price_shock, rule_based_hedge,
)


def test_target_price_rounds_down_then_subtracts_200():
    assert initial_target_price(2857.1) == 2600
    assert initial_target_price(4745.1) == 4500
    assert initial_target_price(100) == 0


def test_monday_of_week():
    assert monday_of_week(datetime(2025, 2, 5)).isoformat() == "2025-02-03"   # a Wednesday
    assert monday_of_week(datetime(2025, 2, 3)).isoformat() == "2025-02-03"


def test_hedge_cleared_only_on_a_new_monday():
    v = init_vault(3000)
    v.hedge_position = 10
    start = monday_of_week(datetime(2025, 2, 3))
    assert apply_weekly_hedge_expiry(v, datetime(2025, 2, 5), start) == start
    assert v.hedge_position == 10
    assert apply_weekly_hedge_expiry(v, datetime(2025, 2, 10), start).isoformat() == "2025-02-10"
    assert v.hedge_position == 0
    assert apply_weekly_hedge_expiry(v, datetime(2025, 2, 10), None).isoformat() == "2025-02-10"


def test_mark_to_market():
    assert hedge_mark_to_market(100, 0.25) == 25
    assert hedge_mark_to_market(100, None) == 0


def test_cvar_is_clipped_stake_weighted_mean_abs_return():
    assert cvar_from_buckets({"<= -10%": 1.0, ">= +10%": 1.0}) == pytest.approx(0.12)
    assert cvar_from_buckets({"-1% to +1% (flat)": 5.0}) == 0.0
    assert cvar_from_buckets({}) == 0.0
    assert C.HEDGE_CVAR_CLIP[1] == 0.60


def test_no_hedge_outside_confidence_band_or_below_min_price():
    for conf, p in [(0.05, 0.3), (0.9, 0.3), (0.5, 0.001)]:
        v = init_vault(3000)
        info = rule_based_hedge(v, p, conf, 0.1)
        assert info["hedge_ratio"] == 0 and v.hedge_position == 0 and v.cash == C.INITIAL_CASH


def test_hedge_is_capped_at_five_percent_of_gold_value_and_cash_adds_up():
    v = init_vault(3000)
    gold = v.units * v.price
    info = rule_based_hedge(v, 0.4, 0.5, 0.6)
    assert info["hedge_value"] <= gold * C.HEDGE_MAX_SPEND_EXPOSURE + 1e-9
    assert v.hedge_position == pytest.approx(info["hedge_value"] / 0.41)
    spent = C.INITIAL_CASH - v.cash
    assert spent == pytest.approx(info["hedge_value"] + info["hedge_fees"] + info["hedge_impact"])
    assert info["hedge_fees"] == pytest.approx(info["hedge_value"] * 5e-4)
    assert info["hedge_impact"] == pytest.approx(info["hedge_value"] * 15e-4)


def test_small_trades_are_skipped():
    v = Vault(units=1.0, price=1000.0, cash=1000.0)         # 5% of 1,000 is 50, below the 250 minimum
    info = rule_based_hedge(v, 0.4, 0.5, 0.6)
    assert info["units_bought"] == 0 and v.cash == 1000.0


def test_gold_is_sold_when_cash_is_short():
    v = Vault(units=10.0, price=1000.0, cash=0.0)
    info = rule_based_hedge(v, 0.4, 0.5, 0.6, max_hedge=0.7)
    assert info["units_sold"] > 0 or info["hedge_value"] < C.HEDGE_MIN_TRADE_USD
    assert v.cash >= 0 and v.units >= 0


def test_shock_resolution():
    v = Vault(units=10, price=1000, cash=500, hedge_position=200)
    hit = resolve_event_with_price_shock(v, True, 0.5)
    assert hit["post_price"] == 500 and hit["hedge_payout"] == 200
    assert hit["final_portfolio"] == 500 + 10 * 500 + 200
    v2 = Vault(units=10, price=1000, cash=500, hedge_position=200)
    miss = resolve_event_with_price_shock(v2, False)
    assert miss["final_portfolio"] == 10500 and miss["hedge_payout"] == 0
