"""Day-by-day backtest of the hedged vault against the same vault left unhedged.

Behaviour matches the original ``run_backtest``: each day the simulated traders bet, the LMSR market
moves, the hedging rule may buy contracts, and every Monday the old contracts are cleared. The market
quantities are never reset and contracts are never settled (see the README).
"""
from __future__ import annotations

import random
from typing import Dict, List, Sequence

from . import config as C
from .data import Prices
from .lmsr import BinaryMarket
from .traders import (
    simulate_market_implied_prob,
    update_usd_strength,
    update_vol_regime,
    vol_scale_from_regime,
)
from .vault import (
    apply_weekly_hedge_expiry,
    hedge_mark_to_market,
    init_vault,
    initial_target_price,
    monday_of_week,
    rule_based_hedge,
)


def max_drawdown(values: Sequence[float]) -> float:
    """Largest fall from a running peak, as a positive fraction."""
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        worst = max(worst, (peak - v) / peak)
    return worst


def unhedged_summary(points: Prices) -> Dict[str, float]:
    start_value = C.INITIAL_CASH + C.INITIAL_UNITS * points[0][1]
    series = [C.INITIAL_CASH + C.INITIAL_UNITS * p for _, p in points]
    return {
        "initial_value": start_value,
        "final_value": series[-1],
        "return": series[-1] / start_value - 1.0,
        "max_drawdown": max_drawdown(series),
    }


def run_backtest(points: Prices, seed: int = 0, bot_count: int = C.SIM_BOT_COUNT) -> dict:
    """Run the hedged vault over ``points`` (a list of (datetime, close)). Returns results and a daily trace."""
    if not points:
        raise ValueError("no prices")
    rng = random.Random(seed)
    first_time, first_price = points[0]
    target_price = initial_target_price(first_price)
    target_week_start = monday_of_week(first_time)
    vault = init_vault(first_price)
    market = BinaryMarket(C.LMSR_B)
    sim_prices: List[float] = []
    usd_strength = C.USD_STRENGTH_CENTER
    vol_regime = "low"
    last_hedge_week_start = target_week_start

    trace = []
    p_bad = 0.0
    for point_time, price in points:
        vault.price = price
        sim_prices.append(price)
        if len(sim_prices) > C.SIM_MEM_SPAN:
            sim_prices = sim_prices[-C.SIM_MEM_SPAN:]
        usd_strength = update_usd_strength(usd_strength, rng)
        if point_time.weekday() == 0 and monday_of_week(point_time) != target_week_start:
            target_price = initial_target_price(price)
            target_week_start = monday_of_week(point_time)
        last_hedge_week_start = apply_weekly_hedge_expiry(vault, point_time, last_hedge_week_start)
        vol_regime = update_vol_regime(vol_regime, rng)
        _, meta = simulate_market_implied_prob(
            price, target_price, None, sim_prices, usd_strength,
            vol_scale_from_regime(vol_regime), rng, bot_count,
        )
        total = meta["down_stake"] + meta["up_stake"]
        if total > 0:
            p_bad = market.add_flow(
                C.LMSR_TRADE_SIZE * meta["down_stake"] / total,
                C.LMSR_TRADE_SIZE * meta["up_stake"] / total,
            )
        else:
            p_bad = market.prices()[0]
        info = rule_based_hedge(vault, p_bad, meta["money_weighted_prob"], meta["cvar"])
        mtm = hedge_mark_to_market(vault.hedge_position, p_bad)
        trace.append({
            "time": point_time, "price": price, "target_price": target_price, "p_bad": p_bad,
            "confidence": meta["money_weighted_prob"], "cvar": meta["cvar"],
            "hedge_ratio": info["hedge_ratio"], "hedge_value": info["hedge_value"],
            "units_sold": info["units_sold"], "units_bought": info["units_bought"],
            "hedge_fees": info["hedge_fees"], "hedge_impact": info["hedge_impact"],
            "units": vault.units, "cash": vault.cash, "hedge_position": vault.hedge_position,
            "hedge_mtm": mtm, "portfolio_value": vault.cash + vault.units * vault.price + mtm,
        })

    initial_value = C.INITIAL_CASH + C.INITIAL_UNITS * first_price
    final_value = trace[-1]["portfolio_value"]
    values = [t["portfolio_value"] for t in trace]
    bought = [t for t in trace if t["units_bought"] > 0]
    return {
        "seed": seed,
        "bot_count": bot_count,
        "steps": len(points),
        "start_price": first_price,
        "end_price": points[-1][1],
        "target_price": target_price,
        "initial_value": initial_value,
        "final_value": final_value,
        "return": final_value / initial_value - 1.0,
        "max_drawdown": max_drawdown(values),
        "final_units": vault.units,
        "final_cash": vault.cash,
        "final_hedge": vault.hedge_position,
        "hedge_days": len(bought),
        "first_hedge": bought[0]["time"] if bought else None,
        "last_hedge": bought[-1]["time"] if bought else None,
        "hedge_spend": sum(t["hedge_value"] for t in bought),
        "hedge_costs": sum(t["hedge_fees"] + t["hedge_impact"] for t in trace),
        "final_p_bad": p_bad,
        "trace": trace,
    }
