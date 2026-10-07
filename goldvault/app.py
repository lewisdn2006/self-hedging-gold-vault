"""Streamlit demo:  streamlit run goldvault/app.py

Replays gold prices one bar per refresh. Each bar the simulated traders bet, the prediction market
moves, and the hedging rule may buy protection for the vault. Uses the bundled daily prices by default
(works offline); tick the box in the sidebar for hourly prices from Yahoo Finance.
"""
from __future__ import annotations

import os
import random
import sys

if __package__ in (None, ""):                      # allow `streamlit run goldvault/app.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from goldvault import config as C
from goldvault.backtest import run_backtest
from goldvault.data import load_prices_csv
from goldvault.lmsr import BinaryMarket
from goldvault.traders import (
    simulate_market_implied_prob, update_usd_strength, update_vol_regime, vol_scale_from_regime,
)
from goldvault.vault import (
    Vault, apply_weekly_hedge_expiry, hedge_mark_to_market, init_vault, initial_target_price,
    monday_of_week, resolve_event_with_price_shock, rule_based_hedge,
)

try:
    from streamlit_autorefresh import st_autorefresh
except ModuleNotFoundError:
    st_autorefresh = None

APP_TITLE = "Self-Hedging Gold Vault"
REFRESH_SECONDS = 10
DEMO_BOTS = 2000                       # fewer traders than the backtest so that each refresh is quick


def money(value: float) -> str:
    return f"{value:,.2f} USD"


@st.cache_data(ttl=3600)
def live_hourly_prices():
    import yfinance as yf

    data = yf.download(C.YFINANCE_TICKER, period="10d", interval="1h", progress=False)
    if data is None or data.empty:
        return []
    close = data["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return [(ts.to_pydatetime().replace(tzinfo=None), float(p)) for ts, p in zip(close.index, close.to_numpy().flatten())]


def init_state() -> None:
    if "vault" in st.session_state:
        return
    st.session_state.update(
        vault=init_vault(), market=BinaryMarket(C.LMSR_B), rng=random.Random(0), index=0,
        sim_prices=[], last_prob=None, usd=C.USD_STRENGTH_CENTER, regime="low",
        target=None, target_week=None, last_hedge_week=None, history=[], snapshots=[],
        last_tick=None, initial_price=None, started=False,
    )


def current_bar(points):
    i = min(st.session_state.index, len(points) - 1)
    return points[i]


def advance(points, tick) -> None:
    if tick is not None and tick != st.session_state.last_tick:
        st.session_state.last_tick = tick
        st.session_state.index = min(st.session_state.index + 1, len(points) - 1)


def main() -> None:
    st.title(APP_TITLE)
    init_state()
    S = st.session_state
    vault: Vault = S.vault
    rng: random.Random = S.rng

    use_live = st.sidebar.checkbox("Use live hourly prices (Yahoo Finance)", value=False)
    points = live_hourly_prices() if use_live else load_prices_csv()
    if not points:
        st.warning("No prices returned.")
        return

    tick = st_autorefresh(interval=REFRESH_SECONDS * 1000, key="refresh") if st_autorefresh else None
    if st_autorefresh is None:
        st.sidebar.warning("Install streamlit-autorefresh for automatic stepping.")
    if not S.started:                               # the first run shows bar 1; later ticks step forward
        S.started, S.last_tick = True, tick
    if st.sidebar.button("Step one bar"):
        tick = (S.last_tick or 0) + 1
    advance(points, tick)

    when, price = current_bar(points)
    vault.price = price
    if S.initial_price is None:
        S.initial_price = price
    if S.target is None:
        S.target, S.target_week = initial_target_price(price), monday_of_week(when)
    elif when.weekday() == 0 and S.target_week != monday_of_week(when):
        S.target, S.target_week = initial_target_price(price), monday_of_week(when)
    S.last_hedge_week = apply_weekly_hedge_expiry(vault, when, S.last_hedge_week)

    S.regime = update_vol_regime(S.regime, rng)
    S.usd = update_usd_strength(S.usd, rng)
    S.sim_prices = (S.sim_prices + [price])[-C.SIM_MEM_SPAN:]
    prob, meta = simulate_market_implied_prob(
        price, S.target, S.last_prob, S.sim_prices, S.usd, vol_scale_from_regime(S.regime), rng, DEMO_BOTS)
    S.last_prob = prob
    total = meta["down_stake"] + meta["up_stake"]
    p_bad = S.market.add_flow(
        C.LMSR_TRADE_SIZE * meta["down_stake"] / total, C.LMSR_TRADE_SIZE * meta["up_stake"] / total
    ) if total > 0 else S.market.prices()[0]

    left, right = st.columns([2, 1])
    with left:
        st.metric("Gold holdings", f"{vault.units:.2f} oz")
        st.metric("Gold price", money(price))
        st.metric("Cash balance", money(vault.cash))
        st.metric("Total account value", money(vault.cash + vault.units * vault.price))
        st.metric("Hedge contracts", f"{vault.hedge_position:.2f}")
    with right:
        st.caption(f"Bar {S.index + 1} of {len(points)}: {when:%Y-%m-%d %H:%M}")
        st.metric("Weekly target price", money(S.target))
        st.metric("Market price of 'gold falls to target' (LMSR)", f"{p_bad:.3f}")
        st.caption(
            f"Traders: {DEMO_BOTS:,} | confidence {meta['money_weighted_prob']:.3f} | "
            f"CVaR* {meta['cvar']:.3f} | USD strength {S.usd:.3f}"
        )
        bucket = pd.DataFrame({"Bucket": list(meta["bucket_totals"]), "Stake": list(meta["bucket_totals"].values())})
        st.dataframe(bucket, hide_index=True)

    def run_hedge() -> None:
        vault.units, vault.cash, vault.hedge_position = C.INITIAL_UNITS, C.INITIAL_CASH, 0.0
        info = rule_based_hedge(vault, p_bad, meta["money_weighted_prob"], meta["cvar"])
        S.history.append(info)
        S.snapshots.append({"bar": S.index, "p_bad": p_bad, "cash": vault.cash,
                            "hedge_mtm": hedge_mark_to_market(vault.hedge_position, p_bad),
                            "portfolio_value": vault.value(p_bad)})
        st.write("Hedge action:", info)

    if st.checkbox("Run the hedge rule on every new bar", value=False) and tick is not None:
        run_hedge()
    if st.button("Run hedge rule now"):
        run_hedge()

    st.write("---")
    st.header("Portfolio timeline")
    if S.snapshots:
        df = pd.DataFrame(S.snapshots)
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(df["bar"], df["portfolio_value"], label="Hedged portfolio")
        ax.axhline(C.INITIAL_CASH + C.INITIAL_UNITS * S.initial_price, color="grey", label="Start")
        ax.set_xlabel("Bar")
        ax.set_ylabel("Portfolio value (USD)")
        ax.legend()
        st.pyplot(fig)
    else:
        st.info("Run the hedge rule to start the timeline.")

    st.write("---")
    st.header("Simulate event outcome")
    occurs = st.checkbox("Event occurs (gold falls to the target)", value=False)
    shock = max(0.0, min(0.99, (price - S.target) / price))
    st.metric(f"Implied drop to {int(S.target)}", f"{shock:.2%}")
    if st.button("Simulate event now"):
        before = vault.value()
        details = resolve_event_with_price_shock(vault, occurs, shock)
        st.write("Resolution details:", details)
        st.metric("Profit / Loss", money(details["final_portfolio"] - before))

    st.write("---")
    st.subheader("Backtest on the bundled prices")
    bots = st.number_input("Simulated traders per day", 100, 10_000, 1000, step=100)
    seed = st.number_input("Random seed", 0, 1000, 0)
    if st.button("Run backtest"):
        with st.spinner("Running backtest..."):
            S.backtest = run_backtest(load_prices_csv(), seed=int(seed), bot_count=int(bots))
    result = S.get("backtest")
    if result:
        st.metric("Final value (hedged)", money(result["final_value"]), f"{result['return']:+.1%}")
        st.write("Worst drawdown:", f"{result['max_drawdown']:.2%}", "| Days a hedge was bought:", result["hedge_days"])
        trace = pd.DataFrame(result["trace"])
        st.download_button("Download backtest trace (CSV)", trace.to_csv(index=False), "backtest_trace.csv", "text/csv")
    st.caption("*'CVaR' here is the stake-weighted mean absolute bucket return, not a tail expectation.")


if __name__ == "__main__":
    main()
