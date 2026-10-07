"""The vault, the weekly target price and the rule that decides how much hedge to buy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from . import config as C


@dataclass
class Vault:
    units: float
    price: float
    cash: float
    hedge_position: float = 0.0

    def value(self, p_bad: Optional[float] = None) -> float:
        """Cash plus gold plus the hedge marked at the market's price of the bad event."""
        return self.cash + self.units * self.price + hedge_mark_to_market(self.hedge_position, p_bad)


def init_vault(price: float = C.DEFAULT_SPOT_FALLBACK) -> Vault:
    return Vault(units=C.INITIAL_UNITS, price=price, cash=C.INITIAL_CASH)


def hedge_mark_to_market(hedge_position: float, p_bad: Optional[float]) -> float:
    if p_bad is None:
        return 0.0
    return hedge_position * C.HEDGE_PAYOUT * p_bad


def monday_of_week(value: datetime) -> date:
    return (value - timedelta(days=value.weekday())).date()


def initial_target_price(spot_price: float) -> float:
    """Weekly "bad event" level: the spot price rounded down to a hundred, less 200."""
    rounded = (spot_price // 100) * 100
    return max(0.0, rounded - 200)


def apply_weekly_hedge_expiry(vault: Vault, spot_time: datetime, last_week_start: Optional[date]) -> date:
    """On the first bar of a new week the hedge is cleared (it is not settled, see the README)."""
    week_monday = monday_of_week(spot_time)
    if last_week_start is None:
        return week_monday
    if spot_time.weekday() == 0 and week_monday != last_week_start:
        vault.hedge_position = 0.0
        return week_monday
    return last_week_start


def cvar_from_buckets(bucket_totals: Dict[str, float]) -> float:
    """Stake-weighted mean absolute bucket return, clipped to HEDGE_CVAR_CLIP.

    Despite the name, this is not an expected loss in the tail; the name is kept from the original.
    """
    total_stake = sum(bucket_totals.values()) or 1.0
    weighted = 0.0
    for label, stake in bucket_totals.items():
        weighted += abs(C.BUCKET_REPRESENTATIVE_RETURN.get(label, 0.0)) * stake
    value = weighted / max(total_stake, 1e-9)
    low, high = C.HEDGE_CVAR_CLIP
    return max(low, min(high, value))


def rule_based_hedge(
    vault: Vault,
    p_bad: float,
    confidence: float,
    cvar: float,
    max_hedge: float = C.HEDGE_MAX_FRACTION,
) -> dict:
    """Buy "gold falls" contracts if the rule allows. Changes ``vault`` and returns what it did."""
    portfolio_value = vault.cash + vault.units * vault.price
    exposure_pct = 0.0 if portfolio_value <= 0 else (vault.units * vault.price) / portfolio_value

    if (
        confidence < C.HEDGE_CONFIDENCE_MIN
        or confidence > C.HEDGE_CONFIDENCE_MAX
        or p_bad < C.HEDGE_MIN_LMSR_PRICE
    ):
        hedge_ratio = 0.0
    else:
        scale = (confidence - C.HEDGE_CONFIDENCE_MIN) / (C.HEDGE_CONFIDENCE_MAX - C.HEDGE_CONFIDENCE_MIN)
        hedge_ratio = min(exposure_pct * cvar * scale, max_hedge)

    hedge_value = hedge_ratio * (vault.units * vault.price)
    hedge_value = min(hedge_value, (vault.units * vault.price) * C.HEDGE_MAX_SPEND_EXPOSURE)

    needed_cash = max(0.0, hedge_value - vault.cash)
    units_to_sell = min(needed_cash / vault.price if vault.price > 0 else 0.0, vault.units)
    vault.units -= units_to_sell
    vault.cash += units_to_sell * vault.price

    unit_price = max(p_bad + C.HEDGE_SPREAD, 1e-6)
    fee_rate = C.HEDGE_FEE_BPS / 10000.0
    impact_rate = C.HEDGE_IMPACT_BPS / 10000.0
    units_bought = hedge_fees = hedge_impact = 0.0
    if hedge_value >= C.HEDGE_MIN_TRADE_USD and vault.cash > 0:
        max_affordable = vault.cash / (1 + fee_rate + impact_rate)
        spend = min(hedge_value, max_affordable)
        units_bought = spend / unit_price
        vault.hedge_position += units_bought
        hedge_fees = spend * fee_rate
        hedge_impact = spend * impact_rate
        vault.cash -= spend + hedge_fees + hedge_impact

    return {
        "hedge_ratio": hedge_ratio,
        "hedge_value": hedge_value,
        "units_sold": units_to_sell,
        "units_bought": units_bought,
        "exposure_pct": exposure_pct,
        "confidence": confidence,
        "cvar": cvar,
        "hedge_fees": hedge_fees,
        "hedge_impact": hedge_impact,
    }


def resolve_event_with_price_shock(vault: Vault, event_occurs: bool, shock_pct: float = 0.5) -> dict:
    """Demo resolution: if the event occurs the gold price falls by ``shock_pct`` and hedges pay 1 each."""
    original_price = vault.price
    payout = 0.0
    if event_occurs:
        vault.price = vault.price * (1.0 - shock_pct)
        payout = vault.hedge_position * C.HEDGE_PAYOUT
    return {
        "event_occurs": event_occurs,
        "original_price": original_price,
        "post_price": vault.price,
        "hedge_payout": payout,
        "final_portfolio": vault.cash + vault.units * vault.price + payout,
    }
