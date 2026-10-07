"""Daily gold futures prices: a bundled CSV for repeatable runs, Yahoo Finance for fresh ones."""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Tuple

from . import config as C

Prices = List[Tuple[datetime, float]]

BUNDLED_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "gold_futures_daily_2025-02-03_to_2026-01-30.csv",
)


def load_prices_csv(path: str = BUNDLED_CSV) -> Prices:
    """Read ``Date,close`` rows. Dates must be strictly increasing and prices positive."""
    points: Prices = []
    with open(path) as handle:
        header = handle.readline().strip().lower().split(",")
        if header[:2] != ["date", "close"]:
            raise ValueError("expected a 'Date,close' header in %s" % path)
        for line in handle:
            line = line.strip()
            if not line:
                continue
            stamp, close = line.split(",")[:2]
            when = datetime.strptime(stamp[:10], "%Y-%m-%d")
            price = float(close)
            if price <= 0:
                raise ValueError("non-positive price on %s" % stamp)
            if points and when <= points[-1][0]:
                raise ValueError("dates not increasing at %s" % stamp)
            points.append((when, price))
    if not points:
        raise ValueError("no prices in %s" % path)
    return points


def fetch_prices_yfinance(start_date: str = C.BACKTEST_START_DATE, end_date: str = C.BACKTEST_END_DATE) -> Prices:
    """Download daily closes of gold futures (needs the optional ``yfinance`` package)."""
    import yfinance as yf

    data = yf.download(C.YFINANCE_TICKER, start=start_date, end=end_date, interval="1d", progress=False)
    if data is None or data.empty:
        return []
    close = data["Close"].dropna()
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return [(ts.to_pydatetime(), float(p)) for ts, p in zip(close.index, close.to_numpy().flatten())]
