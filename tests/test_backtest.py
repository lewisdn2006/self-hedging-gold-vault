import os
from datetime import datetime

import pytest

from goldvault import config as C
from goldvault.backtest import max_drawdown, run_backtest, unhedged_summary
from goldvault.data import BUNDLED_CSV, load_prices_csv


@pytest.fixture(scope="module")
def prices():
    return load_prices_csv()


@pytest.fixture(scope="module")
def run(prices):
    return run_backtest(prices, seed=0, bot_count=300)


def test_bundled_data(prices):
    assert len(prices) == 251
    assert prices[0][1] == pytest.approx(2857.10, abs=0.01) and prices[-1][1] == pytest.approx(4745.10, abs=0.01)


def test_loader_rejects_bad_files(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\n2025-01-01,1\n")
    with pytest.raises(ValueError):
        load_prices_csv(str(p))
    p.write_text("Date,close\n2025-01-02,1\n2025-01-01,2\n")
    with pytest.raises(ValueError):
        load_prices_csv(str(p))
    p.write_text("Date,close\n2025-01-01,-1\n")
    with pytest.raises(ValueError):
        load_prices_csv(str(p))
    p.write_text("Date,close\n")
    with pytest.raises(ValueError):
        load_prices_csv(str(p))


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(0.25)
    assert max_drawdown([1, 2, 3]) == 0


def test_unhedged_summary(prices):
    s = unhedged_summary(prices)
    assert s["return"] == pytest.approx(0.4895, abs=1e-4) and s["max_drawdown"] == pytest.approx(0.0907, abs=1e-4)


def test_same_seed_same_result_and_different_seed_differs(prices):
    a = run_backtest(prices[:60], seed=5, bot_count=200)
    b = run_backtest(prices[:60], seed=5, bot_count=200)
    c = run_backtest(prices[:60], seed=6, bot_count=200)
    assert a["final_value"] == b["final_value"]
    assert a["final_value"] != c["final_value"]


def test_accounting_every_day(run):
    for t in run["trace"]:
        assert t["portfolio_value"] == pytest.approx(t["cash"] + t["units"] * t["price"] + t["hedge_mtm"])
        assert t["cash"] >= 0 and t["units"] >= 0 and t["hedge_position"] >= 0
        assert 0 <= t["p_bad"] <= 1


def test_value_lost_is_only_what_the_hedge_cost(prices):
    r = run_backtest(prices[:15], seed=2, bot_count=300)
    last = r["trace"][-1]
    gold_pnl = C.INITIAL_UNITS * (last["price"] - prices[0][1])
    spent = r["initial_value"] - (last["cash"] + last["units"] * prices[0][1])
    assert last["portfolio_value"] == pytest.approx(r["initial_value"] + gold_pnl - spent + last["hedge_mtm"])


def test_hedge_is_cleared_on_mondays(prices, run):
    seen = False
    for prev, cur in zip(run["trace"], run["trace"][1:]):
        if cur["time"].weekday() == 0 and prev["hedge_position"] > 0 and cur["units_bought"] == 0:
            assert cur["hedge_position"] == 0
            seen = True
    assert seen


def test_hedge_costs_are_fees_plus_impact(run):
    assert run["hedge_costs"] == pytest.approx(sum(t["hedge_fees"] + t["hedge_impact"] for t in run["trace"]))
    assert run["hedge_costs"] <= 0.002 * run["hedge_spend"] + 1e-9


def test_empty_prices_rejected():
    with pytest.raises(ValueError):
        run_backtest([])


@pytest.mark.slow
def test_reproduces_original_reference_run(prices):
    """The original main.py with random.seed(0) gave 554,205 (+43.7%), drawdown 9.37%, 16 hedge days."""
    r = run_backtest(prices, seed=0, bot_count=10_000)
    assert r["final_value"] == pytest.approx(554_205, abs=1)
    assert r["max_drawdown"] == pytest.approx(0.0937, abs=5e-5)
    assert r["hedge_days"] == 16
