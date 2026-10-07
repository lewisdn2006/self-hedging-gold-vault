import random

import pytest

from goldvault import config as C
from goldvault.traders import (
    assign_bucket, belief_to_expected_return, clamp01, momentum_signal, risk_adjust,
    simulate_market_implied_prob, soften_belief, stake_for_confidence, strength_signal,
    update_usd_strength, update_vol_regime, vol_scale_from_regime,
)


@pytest.mark.parametrize("ret,label", [
    (-0.2, "<= -10%"), (-0.10, "<= -10%"), (-0.07, "-10% to -5%"), (-0.04, "-5% to -3%"),
    (-0.02, "-3% to -1%"), (0.0, "-1% to +1% (flat)"), (0.01, "-1% to +1% (flat)"),
    (0.02, "+1% to +3%"), (0.04, "+3% to +5%"), (0.08, "+5% to +10%"), (0.10, "+5% to +10%"),
    (0.11, ">= +10%"),
])
def test_assign_bucket(ret, label):
    assert assign_bucket(ret) == label


def test_every_return_lands_in_exactly_one_bucket():
    labels = {l for l, _, _ in C.SIM_BUCKETS}
    for i in range(-300, 301):
        assert assign_bucket(i / 1000) in labels


def test_signals_need_three_prices():
    assert momentum_signal([1, 2]) == 0 and strength_signal([1, 2]) == 0
    assert momentum_signal([100, 101, 110]) == pytest.approx(0.10)
    assert strength_signal([100, 100, 106]) == pytest.approx(4 / 102)


def test_beliefs_are_softened_and_risk_adjusted():
    assert soften_belief(1.0) == pytest.approx(0.8) and soften_belief(0.5) == 0.5
    assert risk_adjust(0.8, "risk_averse") == pytest.approx(0.6)
    assert risk_adjust(0.8, "risk_seeking") == pytest.approx(0.905)
    assert risk_adjust(0.8, "noise") == 0.8
    assert clamp01(-1) == 0 and clamp01(2) == 1


def test_stake_and_expected_return():
    assert stake_for_confidence(0.5) == 50.0
    assert stake_for_confidence(1.0) == pytest.approx(100 * (0.5 + 1.2))
    assert belief_to_expected_return(0.5, 0.01, 0.1) == 0.01
    assert belief_to_expected_return(1.0, 0.0, 0.1) < 0 < belief_to_expected_return(0.0, 0.0, 0.1)


def test_usd_strength_and_regime_stay_in_range():
    rng = random.Random(0)
    u = 1.0
    for _ in range(2000):
        u = update_usd_strength(u, rng)
        assert 0.85 <= u <= 1.15
    switches = sum(update_vol_regime("low", rng) == "high" for _ in range(4000))
    assert switches / 4000 == pytest.approx(C.REGIME_SWITCH_PROB, abs=0.015)
    assert vol_scale_from_regime("high") > vol_scale_from_regime("low")


def day(spot=4000.0, target=3800.0, seed=0, bots=500, last=None):
    return simulate_market_implied_prob(spot, target, last, [spot] * 5, 1.0, 1.0, random.Random(seed), bots)


def test_one_day_is_repeatable_and_in_range():
    a, ma = day(seed=3)
    b, mb = day(seed=3)
    assert a == b and ma == mb
    assert 0 <= a <= 1
    assert ma["down_stake"] + ma["up_stake"] == pytest.approx(ma["total_stake"])
    assert 0 <= ma["money_weighted_prob"] <= 1 and 0 <= ma["cvar"] <= 0.6


def test_every_bot_places_one_stake():
    _, m = day(bots=1000)
    stakes = m["total_stake"]
    assert 1000 * 50 <= stakes <= 1000 * 170           # per-bot stake is between 50 and 170


def test_price_nearer_target_means_higher_probability_of_falling():
    near = day(spot=4000, target=3960, bots=3000)[1]["base_prob"]
    far = day(spot=4000, target=3000, bots=3000)[1]["base_prob"]
    assert near == pytest.approx(0.01) and far == pytest.approx(0.25)


def test_smoothing_blends_with_last_probability():
    raw = day(seed=1)[1]["raw_prob"]
    smoothed, _ = day(seed=1, last=0.9)
    assert smoothed == pytest.approx(0.85 * raw + 0.15 * 0.9)
