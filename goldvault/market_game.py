"""One person betting against the prediction market (the logic behind the Tkinter demo)."""
from __future__ import annotations

import random
from typing import Optional, Tuple

from .lmsr import BinaryMarket


class MarketGame:
    def __init__(self, liquidity: float = 120.0, cash: float = 100.0, threshold: float = 2000.0) -> None:
        if cash <= 0:
            raise ValueError("cash must be positive")
        self.market = BinaryMarket(liquidity)
        self.cash = float(cash)
        self.shares = [0.0, 0.0]
        self.threshold = float(threshold)

    def place_bet(self, index: int, amount: float) -> Tuple[float, float]:
        """Spend up to ``amount`` on outcome ``index`` (0 YES, 1 NO). Returns (shares bought, cost)."""
        if index not in (0, 1):
            raise ValueError("index must be 0 (YES) or 1 (NO)")
        if amount <= 0:
            raise ValueError("bet amount must be positive")
        if amount > self.cash:
            raise ValueError("not enough cash")
        delta = self.market.delta_for_cost(index, amount)
        cost = self.market.trade(index, delta)
        self.cash -= cost
        self.shares[index] += delta
        return delta, cost

    def resolve(self, rng: Optional[random.Random] = None) -> Tuple[bool, float]:
        """Draw the outcome from the market's own YES probability and pay out. Returns (yes?, payout).

        This is a simulation of resolution: it does not look at a gold price.
        """
        rng = rng or random.Random()
        outcome_yes = rng.random() < self.market.prices()[0]
        payout = self.shares[0] if outcome_yes else self.shares[1]
        self.cash += payout
        self.market.reset()
        self.shares = [0.0, 0.0]
        return outcome_yes, payout
