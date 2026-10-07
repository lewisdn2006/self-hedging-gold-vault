"""Backtest with weekly contracts that are settled, a market that restarts every week, and a real CVaR.

Each Monday (the first bar of a week):
  1. last week's contracts are settled: they pay 1 each if the last close of that week was at or below
     that week's target, and 0 otherwise, and the cash goes into the vault;
  2. the prediction market restarts at 50/50;
  3. a new target is set.
During the week the simulated traders bet each day and the hedging rule may buy contracts, sized with the
trailing 250-bar 5% CVaR of weekly gold returns. Contracts are marked at the market price until settled.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from . import config as C
from .backtest import max_drawdown
from .data import Prices
from .lmsr import BinaryMarket
from .risk import DEFAULT_CVAR, historical_cvar, implied_tail_cvar, tail_cvar
from .traders import (
    simulate_market_implied_prob, update_usd_strength, update_vol_regime, vol_scale_from_regime,
)
from .vault import (
    Vault, hedge_mark_to_market, initial_target_price, monday_of_week, rule_based_hedge,
)

START_GOLD_VALUE = 285_710.0          # gold worth the same share of the vault as in the original run


def weekly_target(spot: float, target_drop: Optional[float]) -> float:
    """The level gold must close at or below for the contract to pay.

    ``target_drop`` is a fraction (0.05 = 5% below spot). ``None`` uses the original rule (spot rounded
    down to a hundred, less 200), which only makes sense when gold is a few thousand dollars.
    """
    if target_drop is None:
        return initial_target_price(spot)
    return spot * (1.0 - target_drop)


def _weeks(points: Prices) -> List[List[int]]:
    groups: List[List[int]] = []
    last = None
    for i, (t, _) in enumerate(points):
        wk = monday_of_week(t)
        if wk != last:
            groups.append([])
            last = wk
        groups[-1].append(i)
    return groups


def run_weekly_backtest(
    points: Prices,
    seed: int = 0,
    bot_count: int = 1000,
    target_drop: Optional[float] = 0.05,
    gold_value: float = START_GOLD_VALUE,
    hedge: str = "market",
    cvar_source: str = "historical",
    history: Optional[List[float]] = None,
) -> dict:
    """Run one window. ``hedge`` is "market" (the real rule), "oracle" (knows each week's outcome) or "none".

    ``history`` is gold closes before the window, used only to warm up the CVaR estimate.
    """
    if hedge not in ("market", "oracle", "none"):
        raise ValueError("hedge must be market, oracle or none")
    if cvar_source not in ("historical", "implied", "original"):
        raise ValueError("cvar_source must be historical, implied or original")
    if not points:
        raise ValueError("no prices")

    rng = random.Random(seed)
    first_price = points[0][1]
    vault = Vault(units=gold_value / first_price, price=first_price, cash=C.INITIAL_CASH)
    initial_value = vault.cash + vault.units * first_price
    units0 = vault.units
    market = BinaryMarket(C.LMSR_B)
    closes: List[float] = list(history or [])
    sim_prices: List[float] = []
    usd = C.USD_STRENGTH_CENTER
    regime = "low"
    p_bad = 0.5

    week_ends = {g[-1] for g in _weeks(points)}
    week_of = {}
    for gi, g in enumerate(_weeks(points)):
        for i in g:
            week_of[i] = gi
    week_last_close = {gi: points[g[-1]][1] for gi, g in enumerate(_weeks(points))}

    cur_week = -1
    target = 0.0
    week_premium = 0.0
    weeks: List[dict] = []
    trace: List[dict] = []
    hedge_days = 0
    unhedged_value: List[float] = []
    week_end_values: List[float] = []

    def settle() -> None:
        nonlocal week_premium
        event = week_last_close[cur_week] <= target
        payout = vault.hedge_position * C.HEDGE_PAYOUT if event else 0.0
        vault.cash += payout
        weeks.append({"week": cur_week, "target": target, "close": week_last_close[cur_week], "event": event,
                      "contracts": vault.hedge_position, "premium": week_premium, "payout": payout})
        vault.hedge_position = 0.0
        week_premium = 0.0

    for i, (when, price) in enumerate(points):
        if week_of[i] != cur_week:
            if cur_week >= 0:
                settle()
            cur_week = week_of[i]
            target = weekly_target(price, target_drop)
            market.reset()
            p_bad = 0.5
        vault.price = price
        closes.append(price)
        sim_prices = (sim_prices + [price])[-C.SIM_MEM_SPAN:]
        usd = update_usd_strength(usd, rng)
        regime = update_vol_regime(regime, rng)
        _, meta = simulate_market_implied_prob(
            price, target, None, sim_prices, usd, vol_scale_from_regime(regime), rng, bot_count)
        total = meta["down_stake"] + meta["up_stake"]
        if total > 0:
            p_bad = market.add_flow(C.LMSR_TRADE_SIZE * meta["down_stake"] / total,
                                    C.LMSR_TRADE_SIZE * meta["up_stake"] / total)

        spent = bought_today = 0.0
        if hedge != "none":
            if cvar_source == "historical":
                cvar = historical_cvar(closes)
            elif cvar_source == "implied":
                cvar = implied_tail_cvar(meta["bucket_totals"])
            else:
                cvar = meta["cvar"]
            confidence = meta["money_weighted_prob"]
            if hedge == "oracle":
                event_comes = week_last_close[cur_week] <= target
                confidence = 0.5 if event_comes else 0.0
            info = rule_based_hedge(vault, p_bad, confidence, cvar)
            spent = info["cost"]
            bought_today = info["units_bought"]
            week_premium += spent
            if info["units_bought"] > 0:
                hedge_days += 1
        mtm = hedge_mark_to_market(vault.hedge_position, p_bad)
        value = vault.cash + vault.units * price + mtm
        trace.append({"time": when, "price": price, "target": target, "p_bad": p_bad,
                      "hedge_position": vault.hedge_position, "spent": spent, "bought": bought_today, "value": value})
        unhedged_value.append(initial_value + units0 * (price - first_price))
        if i in week_ends:
            week_end_values.append(value)

    settle()                                   # the last week settles too
    final_value = vault.cash + vault.units * points[-1][1]
    trace[-1]["value"] = final_value
    values = [t["value"] for t in trace]
    unh_final = unhedged_value[-1]

    def week_returns(vals: List[float]) -> List[float]:
        return [vals[k + 1] / vals[k] - 1.0 for k in range(len(vals) - 1)]

    wk_hedged = week_end_values[:-1] + [final_value]
    wk_unhedged = [unhedged_value[g[-1]] for g in _weeks(points)]
    hr, ur = week_returns(wk_hedged), week_returns(wk_unhedged)
    premium = sum(w["premium"] for w in weeks)
    payout = sum(w["payout"] for w in weeks)
    return {
        "seed": seed, "steps": len(points), "weeks": len(weeks),
        "start": points[0][0], "end": points[-1][0],
        "gold_return": points[-1][1] / first_price - 1.0,
        "initial_value": initial_value, "final_value": final_value, "unhedged_final": unh_final,
        "return": final_value / initial_value - 1.0, "unhedged_return": unh_final / initial_value - 1.0,
        "max_drawdown": max_drawdown(values), "unhedged_drawdown": max_drawdown(unhedged_value),
        "weekly_cvar": tail_cvar(hr) if hr else 0.0, "unhedged_weekly_cvar": tail_cvar(ur) if ur else 0.0,
        "worst_week": min(hr) if hr else 0.0, "unhedged_worst_week": min(ur) if ur else 0.0,
        "premium": premium, "payout": payout, "net_hedge": payout - premium,
        "contracts_bought": sum(w["contracts"] for w in weeks), "gold_sold_oz": units0 - vault.units,
        "hedge_days": hedge_days, "event_weeks": sum(1 for w in weeks if w["event"]),
        "weeks_with_hedge": sum(1 for w in weeks if w["contracts"] > 0),
        "paid_weeks": sum(1 for w in weeks if w["payout"] > 0),
        "week_log": weeks, "trace": trace, "final_cash": vault.cash, "final_units": vault.units,
    }
