from datetime import datetime, timedelta

import pytest

from goldvault import config as C
from goldvault.data import LONG_CSV, load_prices_csv
from goldvault.weekly import START_GOLD_VALUE, run_weekly_backtest, weekly_target


@pytest.fixture(scope="module")
def year_2013():
    return [p for p in load_prices_csv(LONG_CSV) if p[0].year == 2013]


def synthetic(closes, start=datetime(2024, 1, 1)):
    """One bar per weekday from a Monday."""
    out, d = [], start
    for c in closes:
        while d.weekday() > 4:
            d += timedelta(days=1)
        out.append((d, c))
        d += timedelta(days=1)
    return out


def test_target_rules():
    assert weekly_target(2000.0, 0.05) == pytest.approx(1900.0)
    assert weekly_target(2857.1, None) == 2600
    assert weekly_target(200.0, None) == 0


def test_no_hedge_baseline_is_buy_and_hold(year_2013):
    r = run_weekly_backtest(year_2013, bot_count=200, hedge="none")
    assert r["premium"] == 0 and r["payout"] == 0 and r["hedge_days"] == 0
    assert r["return"] == pytest.approx(r["unhedged_return"])
    assert r["unhedged_return"] == pytest.approx(r["gold_return"] * START_GOLD_VALUE / r["initial_value"])


def test_cash_and_gold_account_for_every_dollar(year_2013):
    early = year_2013[:30]
    r = run_weekly_backtest(early, bot_count=200, hedge="market")
    assert r["gold_sold_oz"] == 0
    assert r["final_cash"] == pytest.approx(C.INITIAL_CASH - r["premium"] + r["payout"])
    gold_pnl = r["final_units"] * (early[-1][1] - early[0][1])
    assert r["final_value"] == pytest.approx(r["initial_value"] + gold_pnl - r["premium"] + r["payout"])
    assert r["premium"] == pytest.approx(sum(t["spent"] for t in r["trace"]))


def test_gold_is_sold_when_the_hedge_uses_up_the_cash(year_2013):
    r = run_weekly_backtest(year_2013, bot_count=200, hedge="market")
    assert r["gold_sold_oz"] > 0
    assert r["final_value"] == pytest.approx(r["final_cash"] + r["final_units"] * year_2013[-1][1])
    assert r["premium"] == pytest.approx(sum(t["spent"] for t in r["trace"]))


def test_contracts_are_settled_not_just_deleted():
    # gold falls 10% in week 2, so the event (close <= 95% of Monday price) happens that week
    closes = [100] * 5 + [100, 98, 96, 93, 90] + [90] * 5
    r = run_weekly_backtest(synthetic(closes), bot_count=200, hedge="oracle", gold_value=100_000)
    events = [w for w in r["week_log"] if w["event"]]
    assert len(events) == 1
    assert events[0]["payout"] == pytest.approx(events[0]["contracts"])      # 1 per contract
    assert events[0]["contracts"] > 0 and events[0]["payout"] > events[0]["premium"]
    assert r["payout"] == pytest.approx(events[0]["payout"])
    assert all(w["payout"] == 0 for w in r["week_log"] if not w["event"])


def test_market_restarts_every_week(year_2013):
    r = run_weekly_backtest(year_2013, bot_count=200, hedge="market")
    first_days = [t for t in r["trace"] if t["time"].weekday() == 0]
    assert first_days and all(0.2 < t["p_bad"] < 0.8 for t in first_days)    # one day's flow from 0.5, never stuck near 0
    # contracts held on the first bar of a week are only the ones bought that day: last week's were settled
    for prev, cur in zip(r["trace"], r["trace"][1:]):
        if cur["time"].weekday() < prev["time"].weekday():
            assert cur["hedge_position"] == pytest.approx(cur["bought"])


def test_oracle_pays_only_when_events_happen(year_2013):
    r = run_weekly_backtest(year_2013, bot_count=200, hedge="oracle")
    assert r["weeks_with_hedge"] <= r["event_weeks"]
    assert r["payout"] > r["premium"] > 0


def test_same_seed_repeats_and_bad_options_rejected(year_2013):
    a = run_weekly_backtest(year_2013[:60], seed=3, bot_count=100)
    b = run_weekly_backtest(year_2013[:60], seed=3, bot_count=100)
    assert a["final_value"] == b["final_value"]
    with pytest.raises(ValueError):
        run_weekly_backtest(year_2013, hedge="x")
    with pytest.raises(ValueError):
        run_weekly_backtest(year_2013, cvar_source="x")
    with pytest.raises(ValueError):
        run_weekly_backtest([])


def test_cvar_sources_all_run(year_2013):
    for src in ("historical", "implied", "original"):
        r = run_weekly_backtest(year_2013[:80], bot_count=100, cvar_source=src)
        assert r["final_value"] > 0
