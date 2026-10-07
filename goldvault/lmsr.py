"""Binary prediction market priced by the logarithmic market scoring rule (LMSR).

Outcome 0 is YES, outcome 1 is NO. ``liquidity`` is the LMSR parameter b: the larger it is, the more
money it takes to move the price.
"""
from __future__ import annotations

import math
from typing import List


class BinaryMarket:
    def __init__(self, liquidity: float = 100.0) -> None:
        if liquidity <= 0:
            raise ValueError("liquidity must be positive")
        self.liquidity = float(liquidity)
        self.shares: List[float] = [0.0, 0.0]

    def prices(self) -> List[float]:
        """Probabilities [P(YES), P(NO)]; they sum to 1."""
        top = max(self.shares)
        exp_vals = [math.exp((q - top) / self.liquidity) for q in self.shares]
        denom = sum(exp_vals)
        return [v / denom for v in exp_vals]

    def cost(self, shares: List[float]) -> float:
        """The LMSR cost function C(q) = b ln(sum exp(q_i / b)) for a share vector."""
        top = max(shares)
        total = sum(math.exp((q - top) / self.liquidity) for q in shares)
        return top + self.liquidity * math.log(total)

    def trade(self, index: int, delta: float) -> float:
        """Buy ``delta`` shares of outcome ``index``. Returns what the trade cost."""
        before = self.cost(self.shares)
        new_shares = self.shares[:]
        new_shares[index] += delta
        after = self.cost(new_shares)
        self.shares = new_shares
        return after - before

    def add_flow(self, yes_shares: float, no_shares: float) -> float:
        """Add shares to both outcomes at once and return the new P(YES).

        The vault's simulated traders push the market this way each day.
        """
        self.shares = [self.shares[0] + yes_shares, self.shares[1] + no_shares]
        return self.prices()[0]

    def delta_for_cost(self, index: int, cost_amount: float) -> float:
        """The most shares of ``index`` that cost no more than ``cost_amount``."""
        if cost_amount <= 0.0:
            return 0.0
        lo, hi = 0.0, 1.0
        while self._cost_for_delta(index, hi) < cost_amount:
            hi *= 2.0
            if hi > 1e9:
                break
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self._cost_for_delta(index, mid) <= cost_amount:
                lo = mid
            else:
                hi = mid
        return lo

    def _cost_for_delta(self, index: int, delta: float) -> float:
        new_shares = self.shares[:]
        new_shares[index] += delta
        return self.cost(new_shares) - self.cost(self.shares)

    def reset(self) -> None:
        self.shares = [0.0, 0.0]
