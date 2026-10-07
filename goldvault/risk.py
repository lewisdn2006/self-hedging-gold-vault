"""Tail-risk measures.

``tail_cvar`` is a real conditional value at risk: the average loss in the worst ``alpha`` of outcomes.
The original code's "CVaR" (``vault.cvar_from_buckets``) averaged the absolute return of every bucket.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

from . import config as C

DEFAULT_CVAR = 0.05          # used until there is enough history


def tail_cvar(returns: Sequence[float], alpha: float = 0.05) -> float:
    """Average loss (as a positive fraction) over the worst ``alpha`` share of ``returns``.

    The share is exact: with 100 returns and alpha 5%, it is the mean of the 5 worst. Fractional shares
    of an observation are weighted. Returns 0.0 when even the worst tail is a gain.
    """
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if not returns:
        raise ValueError("no returns")
    ordered = sorted(returns)
    need = alpha * len(ordered)
    taken = 0.0
    total = 0.0
    for r in ordered:
        w = min(1.0, need - taken)
        if w <= 0:
            break
        total += w * r
        taken += w
    return max(0.0, -total / need)


def historical_cvar(closes: Sequence[float], horizon: int = 5, lookback: int = 250, alpha: float = 0.05,
                    min_samples: int = 60) -> float:
    """CVaR of ``horizon``-bar returns over the last ``lookback`` bars of ``closes`` (past data only)."""
    window = closes[-(lookback + horizon):]
    rets = [window[i + horizon] / window[i] - 1.0 for i in range(len(window) - horizon)]
    if len(rets) < min_samples:
        return DEFAULT_CVAR
    return tail_cvar(rets, alpha)


def implied_tail_cvar(bucket_totals: Dict[str, float], alpha: float = 0.05) -> float:
    """CVaR of the return distribution the simulated traders' stakes imply (stake-weighted buckets)."""
    reps: Sequence[Tuple[float, float]] = sorted(
        (C.BUCKET_REPRESENTATIVE_RETURN[label], stake) for label, stake in bucket_totals.items()
    )
    total = sum(s for _, s in reps)
    if total <= 0:
        return 0.0
    need = alpha * total
    taken = acc = 0.0
    for r, stake in reps:
        w = min(stake, need - taken)
        if w <= 0:
            break
        acc += w * r
        taken += w
    return max(0.0, -acc / need)
