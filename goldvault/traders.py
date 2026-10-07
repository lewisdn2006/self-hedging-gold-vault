"""Simulated traders whose bets move the prediction market.

Each of ``bot_count`` bots forms a belief that gold will fall to the weekly target, bets a stake in one
of nine return buckets, and the stakes on the down side and the up side are what move the LMSR price.
All randomness comes from the ``random.Random`` passed in, so a run is repeatable from its seed.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from . import config as C
from .vault import cvar_from_buckets


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def update_usd_strength(prev: float, rng: random.Random) -> float:
    return max(0.85, min(1.15, prev + rng.gauss(0.0, C.USD_STRENGTH_VOL)))


def update_vol_regime(current: str, rng: random.Random) -> str:
    if rng.random() < C.REGIME_SWITCH_PROB:
        return "high" if current == "low" else "low"
    return current


def vol_scale_from_regime(regime: str) -> float:
    return C.REGIME_HIGH_VOL if regime == "high" else C.REGIME_LOW_VOL


def momentum_signal(prices: List[float]) -> float:
    if len(prices) < 3:
        return 0.0
    recent = prices[-min(len(prices), C.SIM_MEM_SPAN):]
    return (recent[-1] - recent[0]) / max(recent[0], 1e-6)


def strength_signal(prices: List[float]) -> float:
    if len(prices) < 3:
        return 0.0
    recent = prices[-min(len(prices), C.SIM_MEM_SPAN):]
    avg = sum(recent) / len(recent)
    return (recent[-1] - avg) / max(avg, 1e-6)


def soften_belief(prob: float) -> float:
    return clamp01(0.5 + (prob - 0.5) * C.SIM_DECISIVENESS)


def risk_adjust(prob: float, profile: str) -> float:
    if profile == "risk_averse":
        return clamp01(prob * 0.75)
    if profile == "risk_seeking":
        return clamp01(0.5 + (prob - 0.5) * 1.35)
    return clamp01(prob)


def assign_bucket(ret: float) -> str:
    for label, low, high in C.SIM_BUCKETS:
        if low is None and high is not None and ret <= high:
            return label
        if high is None and low is not None and ret >= low:
            return label
        if low is not None and high is not None and low < ret <= high:
            return label
    return C.SIM_BUCKETS[-1][0]


def belief_to_expected_return(belief: float, mean_ret: float, vol_ret: float) -> float:
    return mean_ret + (0.5 - belief) * 2.0 * vol_ret


def stake_for_confidence(belief: float) -> float:
    confidence = abs(belief - 0.5) * 2.0
    return C.SIM_BASE_STAKE * (0.5 + C.SIM_CONFIDENCE_SCALE * confidence)


def simulate_market_implied_prob(
    spot_price: float,
    target_price: float,
    last_prob: Optional[float],
    prices: List[float],
    usd_strength: float,
    vol_scale: float,
    rng: random.Random,
    bot_count: int = C.SIM_BOT_COUNT,
) -> Tuple[float, Dict]:
    """One day of betting. Returns (smoothed probability, details including down/up stakes)."""
    base_prob = clamp01((spot_price - target_price) / max(spot_price, 1e-6))

    momentum = momentum_signal(prices)
    strength = strength_signal(prices)
    usd_effect = -(usd_strength - C.USD_STRENGTH_CENTER)
    tech_prob = clamp01(base_prob + 1.5 * momentum + 0.75 * strength)
    fund_prob = clamp01(base_prob + 2.0 * usd_effect + 0.8 * (usd_effect ** 3))
    mean_ret = C.HIST_DAILY_MEAN * C.HIST_HORIZON_DAYS
    vol_ret = C.HIST_DAILY_VOL * (C.HIST_HORIZON_DAYS ** 0.5) * vol_scale

    aggregates: List[float] = []
    placed = 0
    bucket_totals: Dict[str, float] = {label: 0.0 for label, _, _ in C.SIM_BUCKETS}

    for profile, weight in C.SIM_RISK_PROFILES.items():
        n = int(bot_count * weight)
        placed += n

        if profile == "noise":
            beliefs = [rng.random() for _ in range(n)]
        elif profile == "technical":
            beliefs = [tech_prob + rng.gauss(0.0, 0.05) for _ in range(n)]
        elif profile == "fundamental":
            beliefs = [fund_prob + rng.gauss(0.0, 0.03) for _ in range(n)]
        else:
            beliefs = [base_prob + rng.gauss(0.0, 0.04) for _ in range(n)]
            beliefs = [risk_adjust(b, profile) for b in beliefs]

        beliefs = [soften_belief(clamp01(b)) for b in beliefs]
        aggregates.extend(beliefs)
        for b in beliefs:
            expected_ret = belief_to_expected_return(b, mean_ret, vol_ret)
            jitter = rng.gauss(0.0, vol_ret * (0.9 if profile == "noise" else 0.6))
            bucket = assign_bucket(expected_ret + jitter)
            bucket_totals[bucket] += stake_for_confidence(b)

    if placed < bot_count:
        for _ in range(bot_count - placed):
            b = soften_belief(rng.random())
            aggregates.append(b)
            bucket = assign_bucket(belief_to_expected_return(b, mean_ret, vol_ret))
            bucket_totals[bucket] += stake_for_confidence(b)

    avg_belief = sum(aggregates) / max(len(aggregates), 1)
    liquidity_noise = rng.gauss(0.0, 0.02) * C.SIM_LIQUIDITY_SCALE * vol_scale
    raw_prob = clamp01(avg_belief + liquidity_noise)

    down_stake = 0.0
    up_stake = 0.0
    for label, low, high in C.SIM_BUCKETS:
        stake = bucket_totals[label]
        if low is not None and high is not None and low < 0 < high:
            down_stake += 0.5 * stake
            up_stake += 0.5 * stake
        elif high is not None and high <= 0:
            down_stake += stake
        elif low is not None and low >= 0:
            up_stake += stake

    money_weighted_prob = clamp01(down_stake / (down_stake + up_stake + 1e-9))
    raw_prob = clamp01((raw_prob + money_weighted_prob) / 2)
    cvar = cvar_from_buckets(bucket_totals)

    if last_prob is None:
        implied = raw_prob
    else:
        implied = clamp01((1 - C.SIM_PROB_SMOOTHING) * raw_prob + C.SIM_PROB_SMOOTHING * last_prob)

    meta = {
        "base_prob": base_prob,
        "avg_belief": avg_belief,
        "momentum": momentum,
        "strength": strength,
        "usd_strength": usd_strength,
        "raw_prob": raw_prob,
        "implied": implied,
        "bot_count": bot_count,
        "bucket_totals": bucket_totals,
        "money_weighted_prob": money_weighted_prob,
        "down_stake": down_stake,
        "up_stake": up_stake,
        "total_stake": sum(bucket_totals.values()),
        "cvar": cvar,
    }
    return implied, meta
