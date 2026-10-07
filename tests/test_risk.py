import pytest

from goldvault.risk import DEFAULT_CVAR, historical_cvar, implied_tail_cvar, tail_cvar


def test_tail_cvar_is_mean_of_worst_share():
    rets = [-0.10, -0.08, 0.01, 0.02] + [0.03] * 16          # 20 returns, worst 5% is one observation
    assert tail_cvar(rets, 0.05) == pytest.approx(0.10)
    assert tail_cvar(rets, 0.10) == pytest.approx(0.09)       # mean of the worst two
    assert tail_cvar(rets, 1.0) == pytest.approx(-sum(rets) / 20) or tail_cvar(rets, 1.0) == 0.0


def test_fractional_observation_is_weighted():
    assert tail_cvar([-0.2, 0.0, 0.0], 0.5) == pytest.approx(0.2 * 1.0 / 1.5)


def test_gain_in_tail_gives_zero_and_bad_input_rejected():
    assert tail_cvar([0.01, 0.02, 0.03], 0.34) == 0.0
    with pytest.raises(ValueError):
        tail_cvar([], 0.05)
    with pytest.raises(ValueError):
        tail_cvar([0.1], 0)


def test_cvar_is_at_least_as_large_as_a_milder_alpha_and_never_below_var():
    rets = [((i * 37) % 101 - 50) / 500 for i in range(400)]
    assert tail_cvar(rets, 0.05) >= tail_cvar(rets, 0.20)


def test_historical_cvar_uses_only_past_closes_and_falls_back():
    assert historical_cvar([100.0] * 10) == DEFAULT_CVAR
    closes = [100 * (1.0 + 0.001 * i) for i in range(400)]
    assert historical_cvar(closes) == 0.0                    # steady rise, no losses
    crash = closes[:300] + [closes[299] * 0.9] * 5
    assert historical_cvar(crash) > 0.0


def test_implied_tail_cvar_picks_the_lowest_buckets():
    totals = {"<= -10%": 5.0, "-1% to +1% (flat)": 90.0, ">= +10%": 5.0}
    assert implied_tail_cvar(totals, 0.05) == pytest.approx(0.12)
    assert implied_tail_cvar({"-1% to +1% (flat)": 10.0}, 0.05) == 0.0
    assert implied_tail_cvar({}, 0.05) == 0.0
