import math
import random

import pytest

from goldvault.lmsr import BinaryMarket
from goldvault import config as C


def original_update(q_yes, q_no, down, up, b=C.LMSR_B, size=C.LMSR_TRADE_SIZE):
    total = down + up
    if total > 0:
        q_yes += size * down / total
        q_no += size * up / total
    return q_yes, q_no, math.exp(q_yes / b) / (math.exp(q_yes / b) + math.exp(q_no / b))


def test_starts_at_even_odds():
    assert BinaryMarket(100).prices() == [0.5, 0.5]


def test_prices_sum_to_one_and_buying_raises_price():
    m = BinaryMarket(50)
    before = m.prices()[0]
    m.trade(0, 20)
    after = m.prices()
    assert after[0] > before
    assert sum(after) == pytest.approx(1.0)


def test_trade_cost_is_difference_of_cost_function():
    m = BinaryMarket(80)
    m.trade(1, 10)
    c0 = m.cost(m.shares)
    paid = m.trade(0, 7)
    assert paid == pytest.approx(m.cost(m.shares) - c0)


def test_buying_first_share_costs_about_half_for_small_size():
    m = BinaryMarket(1000)
    assert m.trade(0, 1.0) == pytest.approx(0.5, abs=1e-3)


@pytest.mark.parametrize("amount", [0.5, 5, 50])
def test_delta_for_cost_spends_at_most_the_amount(amount):
    m = BinaryMarket(120)
    delta = m.delta_for_cost(0, amount)
    cost = m.trade(0, delta)
    assert cost <= amount + 1e-9
    assert cost == pytest.approx(amount, rel=1e-6)


def test_delta_for_cost_zero():
    assert BinaryMarket(10).delta_for_cost(0, 0) == 0.0


def test_reset():
    m = BinaryMarket(10)
    m.trade(0, 5)
    m.reset()
    assert m.prices() == [0.5, 0.5]


def test_stable_with_huge_quantities():
    m = BinaryMarket(1.0)
    m.shares = [5000.0, 0.0]
    assert m.prices() == pytest.approx([1.0, 0.0])
    assert math.isfinite(m.cost(m.shares))


def test_invalid_liquidity():
    with pytest.raises(ValueError):
        BinaryMarket(0)


def test_add_flow_matches_original_formula():
    rng = random.Random(1)
    m = BinaryMarket(C.LMSR_B)
    q_yes = q_no = 0.0
    for _ in range(300):
        down, up = rng.random() * 1e5, rng.random() * 1e5
        total = down + up
        p = m.add_flow(C.LMSR_TRADE_SIZE * down / total, C.LMSR_TRADE_SIZE * up / total)
        q_yes, q_no, expected = original_update(q_yes, q_no, down, up)
        assert p == pytest.approx(expected, abs=1e-12)
