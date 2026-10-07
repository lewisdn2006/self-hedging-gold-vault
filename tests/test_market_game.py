import random

import pytest

from goldvault.market_game import MarketGame


def test_bet_spends_cash_and_gives_shares():
    g = MarketGame(liquidity=120, cash=100)
    shares, cost = g.place_bet(0, 10)
    assert cost == pytest.approx(10, rel=1e-6)
    assert g.cash == pytest.approx(90, rel=1e-6)
    assert g.shares[0] == shares > 10
    assert g.market.prices()[0] > 0.5


def test_cash_never_negative_when_betting_everything():
    g = MarketGame(cash=100)
    g.place_bet(1, 100)
    assert g.cash >= 0


@pytest.mark.parametrize("amount", [0, -1, 101])
def test_bad_amounts(amount):
    with pytest.raises(ValueError):
        MarketGame(cash=100).place_bet(0, amount)


def test_bad_index():
    with pytest.raises(ValueError):
        MarketGame().place_bet(2, 1)


def test_resolution_pays_winning_side_and_resets():
    g = MarketGame(cash=100)
    g.place_bet(0, 20)
    yes_shares = g.shares[0]
    outcomes = set()
    for seed in range(40):
        h = MarketGame(cash=100)
        h.place_bet(0, 20)
        before = h.cash
        won, payout = h.resolve(random.Random(seed))
        outcomes.add(won)
        assert payout == (yes_shares if won else 0.0)
        assert h.cash == pytest.approx(before + payout)
        assert h.shares == [0.0, 0.0] and h.market.prices() == [0.5, 0.5]
    assert outcomes == {True, False}


def test_yes_wins_in_proportion_to_its_price():
    wins = 0
    for seed in range(2000):
        g = MarketGame(liquidity=10, cash=100)
        g.market.trade(0, 10)      # price of YES about 0.73
        wins += g.resolve(random.Random(seed))[0]
    assert wins / 2000 == pytest.approx(0.731, abs=0.03)
