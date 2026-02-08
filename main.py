# app.py -- Self-Hedging Vault demo (Streamlit)
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import math
import random
import urllib.error
import urllib.request

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ModuleNotFoundError:
    st_autorefresh = None

APP_TITLE = "Self-Hedging Gold Vault"
GOLD_SPOT_URL = "https://api.gold-api.com/price/XAU"
HISTORICAL_START_UK = "2026-02-02 14:00"
USE_HISTORICAL_PRICES = True
YFINANCE_TICKER = "GC=F"
YFINANCE_INTERVAL = "1h"
YFINANCE_LOOKBACK_DAYS = 10
YFINANCE_BACKTEST_INTERVAL = "1d"
BACKTEST_START_DATE = "2025-02-02"
BACKTEST_END_DATE = "2026-02-02"
TARGET_GOLD_PRICE = 4700.0
DEFAULT_SPOT_FALLBACK = 5000.0
REFRESH_SECONDS = 10
HEDGE_PAYOUT = 1.0
OZ_LABEL = "oz"
CURRENCY_LABEL = "USD"

HEDGE_MAX_FRACTION = 0.70
HEDGE_MIN_TRADE_USD = 250.0
HEDGE_CONFIDENCE_FLOOR = 0.1
HEDGE_CVAR_CLIP = (0.0, 0.60)
HEDGE_SPREAD = 0.01
HEDGE_CONFIDENCE_MIN = 0.1
HEDGE_CONFIDENCE_MAX = 0.85
HEDGE_MIN_LMSR_PRICE = 0.005
HEDGE_MAX_SPEND_EXPOSURE = 0.05
HEDGE_FEE_BPS = 5.0
HEDGE_IMPACT_BPS = 15.0
LMSR_B = 2000.0
LMSR_TRADE_SIZE = 1000.0

INITIAL_UNITS = 100.0
INITIAL_PRICE = DEFAULT_SPOT_FALLBACK
INITIAL_CASH = 100000.0

SIM_BOT_COUNT = 10_000
SIM_RISK_PROFILES = {
    "risk_averse": 0.30,
    "risk_neutral": 0.30,
    "risk_seeking": 0.15,
    "noise": 0.15,
    "technical": 0.07,
    "fundamental": 0.03,
}
SIM_LIQUIDITY_SCALE = 1.0
SIM_PROB_SMOOTHING = 0.15
SIM_MEM_SPAN = 20
USD_STRENGTH_CENTER = 1.0
USD_STRENGTH_VOL = 0.03
SIM_BUCKETS = [
    ("<= -10%", None, -0.10),
    ("-10% to -5%", -0.10, -0.05),
    ("-5% to -3%", -0.05, -0.03),
    ("-3% to -1%", -0.03, -0.01),
    ("-1% to +1% (flat)", -0.01, 0.01),
    ("+1% to +3%", 0.01, 0.03),
    ("+3% to +5%", 0.03, 0.05),
    ("+5% to +10%", 0.05, 0.10),
    (">= +10%", 0.10, None),
]
SIM_BASE_STAKE = 100.0
SIM_CONFIDENCE_SCALE = 1.2
SIM_DECISIVENESS = 0.6
HIST_DAILY_MEAN = 0.0004
HIST_DAILY_VOL = 0.0110
HIST_HORIZON_DAYS = 30
REGIME_SWITCH_PROB = 0.05
REGIME_LOW_VOL = 0.8
REGIME_HIGH_VOL = 1.4


@dataclass
class Vault:
    units: float
    price: float
    cash: float
    hedge_position: float = 0.0


def init_vault() -> Vault:
    return Vault(units=INITIAL_UNITS, price=INITIAL_PRICE, cash=INITIAL_CASH)


def ensure_session_state() -> None:
    if "vault" not in st.session_state:
        st.session_state.vault = init_vault()
        st.session_state.history = []
        st.session_state.snapshots = []
        st.session_state.step = 0
        st.session_state.initial_units = INITIAL_UNITS
        st.session_state.initial_cash = INITIAL_CASH
        st.session_state.initial_price = INITIAL_PRICE
        st.session_state.sim_prices = []
        st.session_state.sim_last_prob = None
        st.session_state.usd_strength = USD_STRENGTH_CENTER
        st.session_state.auto_run_hedge = True
        st.session_state.last_auto_run_count = None
        st.session_state.hist_points = []
        st.session_state.hist_index = 0
        st.session_state.target_price = None
        st.session_state.target_week_start = None
        st.session_state.lmsr_q_yes = 0.0
        st.session_state.lmsr_q_no = 0.0
        st.session_state.vol_regime = "low"
        st.session_state.last_hedge_week_start = None


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def format_currency(value: float) -> str:
    return f"{value:,.2f} {CURRENCY_LABEL}"


def _hedge_mark_to_market(hedge_position: float, p_bad: float | None) -> float:
    if p_bad is None:
        return 0.0
    return hedge_position * HEDGE_PAYOUT * p_bad


def record_snapshot(state: Vault, p_bad: float | None, cash_override: float | None = None) -> None:
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = []
    cash_value = state.cash if cash_override is None else cash_override
    hedge_value = _hedge_mark_to_market(state.hedge_position, p_bad)
    st.session_state.snapshots.append(
        {
            "step": st.session_state.get("step", 0),
            "time": utc_now_iso(),
            "p_bad": p_bad,
            "units": state.units,
            "price": state.price,
            "cash": cash_value,
            "hedge_position": state.hedge_position,
            "hedge_mtm": hedge_value,
            "portfolio_value": cash_value + state.units * state.price + hedge_value,
        }
    )
    st.session_state.step = st.session_state.get("step", 0) + 1


def run_keeper_and_record(state: Vault, p_bad: float, P0: float = 0.10, max_hedge: float = 0.5):
    risky_value = state.units * state.price
    hedge_ratio = 0.0
    if p_bad > P0:
        hedge_ratio = min(((p_bad - P0) / (1 - P0)) * max_hedge, max_hedge)
    hedge_value = hedge_ratio * risky_value

    needed_cash = max(0.0, hedge_value - state.cash)
    units_to_sell = min(needed_cash / state.price if state.price > 0 else 0.0, state.units)
    state.units -= units_to_sell
    state.cash += units_to_sell * state.price

    unit_price = max(p_bad, 1e-6)
    units_bought = 0.0
    if hedge_value > 0 and state.cash > 0:
        spend = min(hedge_value, state.cash)
        units_bought = spend / unit_price
        state.hedge_position += units_bought
        state.cash -= spend

    info = {
        "time": utc_now_iso(),
        "hedge_ratio": hedge_ratio,
        "hedge_value": hedge_value,
        "units_sold": units_to_sell,
        "units_bought": units_bought,
    }

    record_snapshot(state, p_bad)
    return info


def _compute_cvar_from_buckets(bucket_totals: dict[str, float]) -> float:
    reps = {
        "<= -10%": -0.12,
        "-10% to -5%": -0.075,
        "-5% to -3%": -0.04,
        "-3% to -1%": -0.02,
        "-1% to +1% (flat)": 0.0,
        "+1% to +3%": 0.02,
        "+3% to +5%": 0.04,
        "+5% to +10%": 0.075,
        ">= +10%": 0.12,
    }
    total_stake = sum(bucket_totals.values()) or 1.0
    weighted_tail = 0.0
    for label, stake in bucket_totals.items():
        r = reps.get(label, 0.0)
        weighted_tail += abs(r) * stake
    cvar = weighted_tail / max(total_stake, 1e-9)
    low, high = HEDGE_CVAR_CLIP
    return max(low, min(high, cvar))


def run_keeper_and_record_rule_based(
    state: Vault,
    p_bad: float,
    confidence: float,
    cvar: float,
    max_hedge: float = HEDGE_MAX_FRACTION,
    record_snapshot_enabled: bool = True,
):
    portfolio_value = state.cash + state.units * state.price
    exposure_pct = 0.0 if portfolio_value <= 0 else (state.units * state.price) / portfolio_value

    if (
        confidence < HEDGE_CONFIDENCE_MIN
        or confidence > HEDGE_CONFIDENCE_MAX
        or p_bad < HEDGE_MIN_LMSR_PRICE
    ):
        hedge_ratio = 0.0
    else:
        confidence_scale = (confidence - HEDGE_CONFIDENCE_MIN) / (HEDGE_CONFIDENCE_MAX - HEDGE_CONFIDENCE_MIN)
        hedge_ratio = exposure_pct * cvar * confidence_scale
        hedge_ratio = min(hedge_ratio, max_hedge)

    hedge_value = hedge_ratio * (state.units * state.price)
    max_spend = (state.units * state.price) * HEDGE_MAX_SPEND_EXPOSURE
    hedge_value = min(hedge_value, max_spend)

    needed_cash = max(0.0, hedge_value - state.cash)
    units_to_sell = min(needed_cash / state.price if state.price > 0 else 0.0, state.units)
    state.units -= units_to_sell
    state.cash += units_to_sell * state.price

    unit_price = max(p_bad + HEDGE_SPREAD, 1e-6)
    units_bought = 0.0
    fee_rate = HEDGE_FEE_BPS / 10000.0
    impact_rate = HEDGE_IMPACT_BPS / 10000.0
    hedge_fees = 0.0
    hedge_impact = 0.0
    if hedge_value >= HEDGE_MIN_TRADE_USD and state.cash > 0:
        max_affordable = state.cash / (1 + fee_rate + impact_rate)
        spend = min(hedge_value, max_affordable)
        units_bought = spend / unit_price
        state.hedge_position += units_bought
        hedge_fees = spend * fee_rate
        hedge_impact = spend * impact_rate
        state.cash -= spend + hedge_fees + hedge_impact

    info = {
        "time": utc_now_iso(),
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

    if record_snapshot_enabled:
        record_snapshot(state, p_bad)
    return info


def resolve_event_with_price_shock(state: Vault, event_occurs: bool, shock_pct: float = 0.5):
    original_price = state.price
    payout = 0.0
    if event_occurs:
        state.price = state.price * (1.0 - shock_pct)
        payout = state.hedge_position * HEDGE_PAYOUT

    final_portfolio = state.cash + state.units * state.price + payout
    record_snapshot(state, None, cash_override=state.cash + payout)

    return {
        "event_occurs": event_occurs,
        "original_price": original_price,
        "post_price": state.price,
        "hedge_payout": payout,
        "final_portfolio": final_portfolio,
    }


def plot_timeline() -> None:
    snaps = st.session_state.get("snapshots", [])
    if not snaps:
        st.info("No snapshots yet. Run the hedge algorithm to create one.")
        return
    df = pd.DataFrame(snaps)
    initial_units = st.session_state.get("initial_units", INITIAL_UNITS)
    initial_cash = st.session_state.get("initial_cash", INITIAL_CASH)
    initial_price = st.session_state.get("initial_price", INITIAL_PRICE)
    df["baseline"] = initial_cash + initial_units * initial_price
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(df.index, df["portfolio_value"], label="Hedged portfolio")
    ax.plot(df.index, df["baseline"], label="Baseline (no hedge)")
    ax.set_xlabel("Hedge step")
    ax.set_ylabel(f"Portfolio value ({CURRENCY_LABEL})")
    ax.legend()
    st.pyplot(fig)


def portfolio_value(v: Vault) -> float:
    return v.cash + v.units * v.price


def final_after_resolution(v: Vault, event_occurs: bool) -> float:
    payout = v.hedge_position * (HEDGE_PAYOUT if event_occurs else 0.0)
    return v.cash + v.units * v.price + payout


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _update_usd_strength(prev: float) -> float:
    shock = random.gauss(0.0, USD_STRENGTH_VOL)
    return max(0.85, min(1.15, prev + shock))


def _lmsr_price(q_yes: float, q_no: float, b: float) -> float:
    exp_yes = math.exp(q_yes / b)
    exp_no = math.exp(q_no / b)
    return exp_yes / (exp_yes + exp_no)


def _update_lmsr(q_yes: float, q_no: float, down_stake: float, up_stake: float) -> tuple[float, float, float]:
    total = down_stake + up_stake
    if total > 0:
        down_share = down_stake / total
        up_share = up_stake / total
        q_yes += LMSR_TRADE_SIZE * down_share
        q_no += LMSR_TRADE_SIZE * up_share
    return q_yes, q_no, _lmsr_price(q_yes, q_no, LMSR_B)


def _compute_initial_target_price(spot_price: float) -> float:
    rounded = (spot_price // 100) * 100
    return max(0.0, rounded - 200)


def _monday_of_week(value: datetime) -> date:
    return (value - timedelta(days=value.weekday())).date()


def _update_target_price_weekly(spot_price: float, spot_time: datetime | None) -> None:
    if spot_time is None:
        return
    week_monday = _monday_of_week(spot_time)
    if st.session_state.get("target_price") is None:
        st.session_state.target_price = _compute_initial_target_price(spot_price)
        st.session_state.target_week_start = week_monday
        return
    if spot_time.weekday() == 0 and st.session_state.get("target_week_start") != week_monday:
        st.session_state.target_price = _compute_initial_target_price(spot_price)
        st.session_state.target_week_start = week_monday


def _update_vol_regime(current: str) -> str:
    if random.random() < REGIME_SWITCH_PROB:
        return "high" if current == "low" else "low"
    return current


def _vol_scale_from_regime(regime: str) -> float:
    return REGIME_HIGH_VOL if regime == "high" else REGIME_LOW_VOL


def _apply_weekly_hedge_expiry(state: Vault, spot_time: datetime, last_week_start: date | None) -> date:
    week_monday = _monday_of_week(spot_time)
    if last_week_start is None:
        return week_monday
    if spot_time.weekday() == 0 and week_monday != last_week_start:
        state.hedge_position = 0.0
        return week_monday
    return last_week_start


def _momentum_signal(prices: list[float]) -> float:
    if len(prices) < 3:
        return 0.0
    recent = prices[-min(len(prices), SIM_MEM_SPAN):]
    delta = recent[-1] - recent[0]
    return delta / max(recent[0], 1e-6)


def _strength_signal(prices: list[float]) -> float:
    if len(prices) < 3:
        return 0.0
    recent = prices[-min(len(prices), SIM_MEM_SPAN):]
    avg = sum(recent) / len(recent)
    return (recent[-1] - avg) / max(avg, 1e-6)


def _soften_belief(prob: float) -> float:
    return _clamp01(0.5 + (prob - 0.5) * SIM_DECISIVENESS)


def _risk_adjust(prob: float, profile: str) -> float:
    if profile == "risk_averse":
        return _clamp01(prob * 0.75)
    if profile == "risk_seeking":
        return _clamp01(0.5 + (prob - 0.5) * 1.35)
    return _clamp01(prob)


def _assign_bucket(ret: float) -> str:
    for label, low, high in SIM_BUCKETS:
        if low is None and high is not None and ret <= high:
            return label
        if high is None and low is not None and ret >= low:
            return label
        if low is not None and high is not None and low < ret <= high:
            return label
    return SIM_BUCKETS[-1][0]


def _belief_to_expected_return(belief: float, mean_ret: float, vol_ret: float) -> float:
    return mean_ret + (0.5 - belief) * 2.0 * vol_ret


def _stake_for_confidence(belief: float) -> float:
    confidence = abs(belief - 0.5) * 2.0
    return SIM_BASE_STAKE * (0.5 + SIM_CONFIDENCE_SCALE * confidence)


def simulate_market_implied_prob(
    spot_price: float,
    target_price: float,
    last_prob: float | None,
    prices: list[float],
    usd_strength: float,
    vol_scale: float,
) -> tuple[float, dict]:
    base_prob = _clamp01((spot_price - target_price) / max(spot_price, 1e-6))

    momentum = _momentum_signal(prices)
    strength = _strength_signal(prices)
    usd_effect = -(usd_strength - USD_STRENGTH_CENTER)
    tech_prob = _clamp01(base_prob + 1.5 * momentum + 0.75 * strength)
    fund_prob = _clamp01(base_prob + 2.0 * usd_effect + 0.8 * (usd_effect ** 3))
    mean_ret = HIST_DAILY_MEAN * HIST_HORIZON_DAYS
    vol_ret = HIST_DAILY_VOL * (HIST_HORIZON_DAYS ** 0.5) * vol_scale

    aggregates = []
    bot_count = 0
    bucket_totals: dict[str, float] = {label: 0.0 for label, _, _ in SIM_BUCKETS}

    for profile, weight in SIM_RISK_PROFILES.items():
        n = int(SIM_BOT_COUNT * weight)
        bot_count += n

        if profile == "noise":
            beliefs = [random.random() for _ in range(n)]
        elif profile == "technical":
            beliefs = [tech_prob + random.gauss(0.0, 0.05) for _ in range(n)]
        elif profile == "fundamental":
            beliefs = [fund_prob + random.gauss(0.0, 0.03) for _ in range(n)]
        else:
            beliefs = [base_prob + random.gauss(0.0, 0.04) for _ in range(n)]
            beliefs = [_risk_adjust(b, profile) for b in beliefs]

        beliefs = [_soften_belief(_clamp01(b)) for b in beliefs]
        aggregates.extend(beliefs)
        for b in beliefs:
            expected_ret = _belief_to_expected_return(b, mean_ret, vol_ret)
            jitter = random.gauss(0.0, vol_ret * (0.9 if profile == "noise" else 0.6))
            bet_ret = expected_ret + jitter
            bucket = _assign_bucket(bet_ret)
            stake = _stake_for_confidence(b)
            bucket_totals[bucket] += stake

    if bot_count < SIM_BOT_COUNT:
        for _ in range(SIM_BOT_COUNT - bot_count):
            b = _soften_belief(random.random())
            aggregates.append(b)
            expected_ret = _belief_to_expected_return(b, mean_ret, vol_ret)
            bucket = _assign_bucket(expected_ret)
            bucket_totals[bucket] += _stake_for_confidence(b)

    avg_belief = sum(aggregates) / max(len(aggregates), 1)
    liquidity_noise = random.gauss(0.0, 0.02) * SIM_LIQUIDITY_SCALE * vol_scale
    raw_prob = _clamp01(avg_belief + liquidity_noise)

    down_stake = 0.0
    up_stake = 0.0
    for label, low, high in SIM_BUCKETS:
        stake = bucket_totals[label]
        if low is not None and high is not None and low < 0 < high:
            down_stake += 0.5 * stake
            up_stake += 0.5 * stake
        elif high is not None and high <= 0:
            down_stake += stake
        elif low is not None and low >= 0:
            up_stake += stake

    money_weighted_prob = _clamp01(down_stake / (down_stake + up_stake + 1e-9))
    raw_prob = _clamp01((raw_prob + money_weighted_prob) / 2)

    cvar = _compute_cvar_from_buckets(bucket_totals)

    if last_prob is None:
        implied = raw_prob
    else:
        implied = _clamp01((1 - SIM_PROB_SMOOTHING) * raw_prob + SIM_PROB_SMOOTHING * last_prob)

    meta = {
        "base_prob": base_prob,
        "avg_belief": avg_belief,
        "momentum": momentum,
        "strength": strength,
        "usd_strength": usd_strength,
        "raw_prob": raw_prob,
        "implied": implied,
        "bot_count": SIM_BOT_COUNT,
        "bucket_totals": bucket_totals,
        "money_weighted_prob": money_weighted_prob,
        "down_stake": down_stake,
        "up_stake": up_stake,
        "total_stake": sum(bucket_totals.values()),
        "cvar": cvar,
    }
    return implied, meta


@st.cache_data(ttl=10)
def fetch_gold_spot_usd():
    try:
        request = urllib.request.Request(
            GOLD_SPOT_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HedgingDemo/1.0)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gold spot fetch failed: {exc}")

    data = json.loads(payload)
    if isinstance(data, dict):
        for key in ("price", "value", "last"):
            if key in data:
                return float(data[key])
    return None


@st.cache_data(ttl=3600)
def fetch_historical_gold_prices(start_dt: datetime) -> list[tuple[datetime, float]]:
    end_dt = datetime.now(timezone.utc)
    yf_start = max(start_dt, end_dt - pd.Timedelta(days=YFINANCE_LOOKBACK_DAYS))
    data = yf.download(
        YFINANCE_TICKER,
        start=yf_start,
        end=end_dt,
        interval=YFINANCE_INTERVAL,
        progress=False,
    )
    if data is None or data.empty:
        data = yf.download(
            YFINANCE_TICKER,
            period=f"{YFINANCE_LOOKBACK_DAYS}d",
            interval=YFINANCE_INTERVAL,
            progress=False,
        )
    if data is None or data.empty:
        return []
    try:
        idx = data.index
        if getattr(idx, "tz", None) is None:
            start_filter = start_dt.replace(tzinfo=None)
        else:
            start_filter = start_dt.astimezone(idx.tz)
        data = data.loc[idx >= start_filter]
    except Exception:
        pass
    close_data = data["Close"].dropna()
    if isinstance(close_data, pd.DataFrame):
        close_data = close_data.iloc[:, 0]
    prices = close_data.to_numpy().flatten().tolist()
    times = close_data.index.to_list()
    points = []
    for ts, price in zip(times, prices):
        ts_value = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        points.append((ts_value, float(price)))
    return points


@st.cache_data(ttl=3600)
def fetch_backtest_prices(start_date: str, end_date: str) -> list[tuple[datetime, float]]:
    data = yf.download(
        YFINANCE_TICKER,
        start=start_date,
        end=end_date,
        interval=YFINANCE_BACKTEST_INTERVAL,
        progress=False,
    )
    if data is None or data.empty:
        return []
    close_data = data["Close"].dropna()
    if isinstance(close_data, pd.DataFrame):
        close_data = close_data.iloc[:, 0]
    prices = close_data.to_numpy().flatten().tolist()
    times = close_data.index.to_list()
    points = []
    for ts, price in zip(times, prices):
        ts_value = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        points.append((ts_value, float(price)))
    return points


def run_backtest(start_date: str, end_date: str) -> dict:
    points = fetch_backtest_prices(start_date, end_date)
    if not points:
        raise RuntimeError("No backtest prices available.")

    first_time, first_price = points[0]
    target_price = _compute_initial_target_price(first_price)
    target_week_start = _monday_of_week(first_time)
    vault = init_vault()
    vault.price = first_price
    sim_prices: list[float] = []
    usd_strength = USD_STRENGTH_CENTER
    q_yes = 0.0
    q_no = 0.0
    vol_regime = "low"
    last_hedge_week_start = target_week_start

    trace = []
    for point in points:
        point_time, price = point
        vault.price = price
        sim_prices.append(price)
        if len(sim_prices) > SIM_MEM_SPAN:
            sim_prices = sim_prices[-SIM_MEM_SPAN:]
        usd_strength = _update_usd_strength(usd_strength)
        if point_time.weekday() == 0 and _monday_of_week(point_time) != target_week_start:
            target_price = _compute_initial_target_price(price)
            target_week_start = _monday_of_week(point_time)
        last_hedge_week_start = _apply_weekly_hedge_expiry(vault, point_time, last_hedge_week_start)
        vol_regime = _update_vol_regime(vol_regime)
        vol_scale = _vol_scale_from_regime(vol_regime)
        sim_prob, sim_meta = simulate_market_implied_prob(
            price,
            target_price,
            None,
            sim_prices,
            usd_strength,
            vol_scale,
        )
        q_yes, q_no, p_bad = _update_lmsr(
            q_yes,
            q_no,
            sim_meta.get("down_stake", 0.0),
            sim_meta.get("up_stake", 0.0),
        )
        info = run_keeper_and_record_rule_based(
            vault,
            p_bad,
            sim_meta.get("money_weighted_prob", 0.0),
            sim_meta.get("cvar", 0.0),
            record_snapshot_enabled=False,
        )
        trace.append(
            {
                "time": point_time,
                "price": price,
                "target_price": target_price,
                "p_bad": p_bad,
                "confidence": sim_meta.get("money_weighted_prob", 0.0),
                "cvar": sim_meta.get("cvar", 0.0),
                "hedge_ratio": info.get("hedge_ratio"),
                "hedge_value": info.get("hedge_value"),
                "units_sold": info.get("units_sold"),
                "units_bought": info.get("units_bought"),
                "hedge_fees": info.get("hedge_fees"),
                "hedge_impact": info.get("hedge_impact"),
                "units": vault.units,
                "cash": vault.cash,
                "hedge_position": vault.hedge_position,
                "hedge_mtm": _hedge_mark_to_market(vault.hedge_position, p_bad),
                "portfolio_value": vault.cash + vault.units * vault.price + _hedge_mark_to_market(vault.hedge_position, p_bad),
            }
        )

    final_value = vault.cash + vault.units * vault.price + _hedge_mark_to_market(vault.hedge_position, p_bad)
    initial_value = INITIAL_CASH + INITIAL_UNITS * first_price
    return {
        "start_date": start_date,
        "end_date": end_date,
        "start_price": first_price,
        "end_price": points[-1][1],
        "target_price": target_price,
        "steps": len(points),
        "initial_value": initial_value,
        "final_value": final_value,
        "delta": final_value - initial_value,
        "final_units": vault.units,
        "final_cash": vault.cash,
        "final_hedge": vault.hedge_position,
        "trace": trace,
    }


def compute_shock_pct(spot_price: float | None) -> float:
    spot_value = spot_price if spot_price and spot_price > 0 else DEFAULT_SPOT_FALLBACK
    target_price = st.session_state.get("target_price") or TARGET_GOLD_PRICE
    return max(0.0, min(0.99, (spot_value - target_price) / spot_value))


def render_metrics(vault: Vault) -> None:
    st.metric("Gold holdings", f"{vault.units:.2f} {OZ_LABEL}")
    st.metric("Spot price", f"{vault.price:,.2f} {CURRENCY_LABEL}")
    st.metric("Cash balance", format_currency(vault.cash))
    st.metric("Total account value", format_currency(vault.cash + vault.units * vault.price))
    st.metric("Hedge contracts", f"{vault.hedge_position:.2f}")


def render_controls(vault: Vault) -> None:
    refresh_count = None
    if st_autorefresh:
        refresh_count = st_autorefresh(interval=int(REFRESH_SECONDS * 1000), key="pm_autorefresh")
    else:
        st.warning("Auto-refresh requires streamlit-autorefresh in this environment.")

    spot_price = None
    spot_err = None
    spot_time = None
    if USE_HISTORICAL_PRICES:
        try:
            start_dt = datetime.strptime(HISTORICAL_START_UK, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            if not st.session_state.get("hist_points"):
                st.session_state.hist_points = fetch_historical_gold_prices(start_dt)
                st.session_state.hist_index = 0
            if not st.session_state.get("hist_points"):
                st.warning("No historical prices returned. Waiting for API...")
                return
            points = st.session_state.hist_points
            idx = min(st.session_state.hist_index, len(points) - 1)
            point = points[idx]
            if isinstance(point, (list, tuple)) and len(point) == 2:
                spot_time, spot_price = point
            else:
                spot_time, spot_price = None, point
            if refresh_count is not None and refresh_count != st.session_state.get("last_hist_refresh"):
                st.session_state.hist_index = min(idx + 1, len(points) - 1)
                st.session_state.last_hist_refresh = refresh_count
        except RuntimeError as exc:
            spot_err = str(exc)
    else:
        try:
            spot_price = fetch_gold_spot_usd()
        except RuntimeError as exc:
            spot_err = str(exc)

    if spot_price is None:
        st.warning(spot_err or "Gold spot price is unavailable. Waiting for API...")
        return

    st.metric("Live gold spot", f"{spot_price:,.2f} {CURRENCY_LABEL}")
    spot_threshold = spot_price
    vault.price = spot_price
    if st.session_state.get("initial_price") == INITIAL_PRICE:
        st.session_state.initial_price = spot_price
    effective_time = spot_time if spot_time is not None else datetime.now(timezone.utc)
    _update_target_price_weekly(spot_price, effective_time)
    st.session_state.last_hedge_week_start = _apply_weekly_hedge_expiry(
        vault,
        effective_time,
        st.session_state.get("last_hedge_week_start"),
    )
    st.session_state.vol_regime = _update_vol_regime(st.session_state.get("vol_regime", "low"))
    vol_scale = _vol_scale_from_regime(st.session_state.vol_regime)
    st.session_state.spot_price = spot_price

    if st.button("Refresh simulated market"):
        st.session_state.sim_last_prob = None
        st.session_state.sim_prices = []
        st.session_state.usd_strength = USD_STRENGTH_CENTER
        st.session_state.lmsr_q_yes = 0.0
        st.session_state.lmsr_q_no = 0.0

    st.session_state.sim_prices.append(spot_threshold)
    if len(st.session_state.sim_prices) > SIM_MEM_SPAN:
        st.session_state.sim_prices = st.session_state.sim_prices[-SIM_MEM_SPAN:]

    st.session_state.usd_strength = _update_usd_strength(st.session_state.usd_strength)

    sim_prob, sim_meta = simulate_market_implied_prob(
        spot_threshold,
        st.session_state.get("target_price") or TARGET_GOLD_PRICE,
        st.session_state.sim_last_prob,
        st.session_state.sim_prices,
        st.session_state.usd_strength,
        vol_scale,
    )
    st.session_state.sim_last_prob = sim_prob

    q_yes, q_no, lmsr_price = _update_lmsr(
        st.session_state.lmsr_q_yes,
        st.session_state.lmsr_q_no,
        sim_meta.get("down_stake", 0.0),
        sim_meta.get("up_stake", 0.0),
    )
    st.session_state.lmsr_q_yes = q_yes
    st.session_state.lmsr_q_no = q_no
    sim_p_bad = lmsr_price

    st.write("Simulated market:", f"{SIM_BOT_COUNT} bots")
    st.metric("Implied probability (LMSR)", f"{sim_p_bad:.3f}")
    st.caption(
        f"Base: {sim_meta['base_prob']:.3f} | "
        f"Momentum: {sim_meta['momentum']:+.3f} | "
        f"Strength: {sim_meta.get('strength', 0.0):+.3f} | "
        f"USD strength: {sim_meta['usd_strength']:.3f} | "
        f"CVaR: {sim_meta['cvar']:.3f} | "
        f"Confidence: {sim_meta['money_weighted_prob']:.3f} | "
        f"LMSR: {sim_p_bad:.3f}"
    )

    bucket_totals = sim_meta.get("bucket_totals", {})
    if bucket_totals:
        bucket_df = (
            pd.DataFrame(
                {
                    "Bucket": list(bucket_totals.keys()),
                    "Stake": list(bucket_totals.values()),
                }
            )
            .assign(Share=lambda d: d["Stake"] / max(sim_meta.get("total_stake", 1.0), 1e-9))
            .sort_values("Bucket")
        )
        st.subheader("Bucketed bets (money-weighted)")
        st.dataframe(bucket_df, width="stretch")

    p = sim_p_bad if sim_p_bad is not None else 0.0
    auto_run = st.checkbox("Auto-run hedge on refresh", value=st.session_state.auto_run_hedge)
    st.session_state.auto_run_hedge = auto_run

    if (
        auto_run
        and sim_p_bad is not None
        and refresh_count is not None
        and refresh_count != st.session_state.get("last_auto_run_count")
    ):
        st.session_state.last_auto_run_count = refresh_count
        vault.units = st.session_state.get("initial_units", INITIAL_UNITS)
        vault.cash = st.session_state.get("initial_cash", INITIAL_CASH)
        vault.hedge_position = 0.0
        vault.price = st.session_state.get("spot_price") or vault.price
        info = run_keeper_and_record_rule_based(
            vault,
            p,
            sim_meta.get("money_weighted_prob", 0.0),
            sim_meta.get("cvar", 0.0),
        )
        st.session_state.history.append(info)

    if st.button("Run hedge algorithm", disabled=sim_p_bad is None):
        vault.units = st.session_state.get("initial_units", INITIAL_UNITS)
        vault.cash = st.session_state.get("initial_cash", INITIAL_CASH)
        vault.hedge_position = 0.0
        vault.price = st.session_state.get("spot_price") or vault.price
        info = run_keeper_and_record_rule_based(
            vault,
            p,
            sim_meta.get("money_weighted_prob", 0.0),
            sim_meta.get("cvar", 0.0),
        )
        st.session_state.history.append(info)
        st.write("Hedge action:", info)


def render_resolution(vault: Vault) -> None:
    st.write("---")
    st.header("Simulate event outcome")
    occurs = st.checkbox("Event occurs (gold drops to target)", value=False)
    target_price = st.session_state.get("target_price") or TARGET_GOLD_PRICE
    shock_pct = compute_shock_pct(st.session_state.get("spot_price"))
    st.metric(f"Implied drop to {int(target_price)}", f"{shock_pct:.2%}")
    if st.button("Simulate event now"):
        pre_value = portfolio_value(vault)
        details = resolve_event_with_price_shock(vault, occurs, shock_pct)
        st.write("Resolution details:", details)
        st.metric("Total money", format_currency(details["final_portfolio"]))
        st.metric("Profit / Loss", format_currency(details["final_portfolio"] - pre_value))


def render_timeline() -> None:
    st.write("---")
    st.header("Portfolio timeline")
    plot_timeline()


def render_summary(vault: Vault) -> None:
    st.write("---")
    st.write("Current portfolio value (no event):", format_currency(portfolio_value(vault)))
    if st.button("Compare vs no-hedge (no shock)"):
        final = final_after_resolution(vault, False)
        baseline = init_vault()
        baseline_value = baseline.cash + baseline.units * baseline.price
        st.write("Final with hedge (no shock):", format_currency(final))
        st.write("Final without hedge:", format_currency(baseline_value))
        st.write("Delta (with - without):", format_currency(final - baseline_value))

    st.write("---")
    st.subheader(f"Backtest ({BACKTEST_START_DATE} to {BACKTEST_END_DATE})")
    if st.button("Run backtest"):
        try:
            with st.spinner("Running backtest..."):
                st.session_state.backtest_result = run_backtest(BACKTEST_START_DATE, BACKTEST_END_DATE)
        except RuntimeError as exc:
            st.warning(str(exc))

    result = st.session_state.get("backtest_result")
    if result:
        st.write("Steps:", result["steps"])
        st.write("Start price:", format_currency(result["start_price"]))
        st.write("End price:", format_currency(result["end_price"]))
        st.write("Target price:", format_currency(result["target_price"]))
        st.metric("Final value", format_currency(result["final_value"]))
        st.metric("Delta", format_currency(result["delta"]))
        trace = result.get("trace", [])
        if trace:
            trace_df = pd.DataFrame(trace)
            st.download_button(
                "Download backtest trace (CSV)",
                data=trace_df.to_csv(index=False),
                file_name="backtest_trace.csv",
                mime="text/csv",
            )


def render_action_log() -> None:
    st.write("---")
    st.subheader("Hedge actions (last 10)")
    for entry in st.session_state.history[-10:]:
        st.write(entry)


def render_export() -> None:
    if st.button("Export snapshots JSON"):
        st.download_button(
            "Download snapshots.json",
            data=pd.DataFrame(st.session_state.snapshots).to_json(orient="records", indent=2),
            file_name="snapshots.json",
            mime="application/json",
        )


def main() -> None:
    st.title(APP_TITLE)
    ensure_session_state()

    vault: Vault = st.session_state.vault

    col1, col2 = st.columns([2, 1])
    with col1:
        render_metrics(vault)
    with col2:
        render_controls(vault)

    render_timeline()
    render_resolution(vault)
    render_summary(vault)
    render_action_log()
    render_export()


if __name__ == "__main__":
    main()
