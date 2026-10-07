"""Settings for the vault, the hedging rule and the simulated traders.

These are the values from the original ``hackathon/main.py``; none has been tuned.
"""
from __future__ import annotations

# Hedge contract and hedging rule
HEDGE_PAYOUT = 1.0
HEDGE_MAX_FRACTION = 0.70
HEDGE_MIN_TRADE_USD = 250.0
HEDGE_CVAR_CLIP = (0.0, 0.60)
HEDGE_SPREAD = 0.01
HEDGE_CONFIDENCE_MIN = 0.1
HEDGE_CONFIDENCE_MAX = 0.85
HEDGE_MIN_LMSR_PRICE = 0.005
HEDGE_MAX_SPEND_EXPOSURE = 0.05
HEDGE_FEE_BPS = 5.0
HEDGE_IMPACT_BPS = 15.0

# Prediction market (LMSR)
LMSR_B = 2000.0
LMSR_TRADE_SIZE = 1000.0

# Starting vault
DEFAULT_SPOT_FALLBACK = 5000.0
INITIAL_UNITS = 100.0
INITIAL_CASH = 100000.0

# Simulated traders
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
BUCKET_REPRESENTATIVE_RETURN = {
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
SIM_BASE_STAKE = 100.0
SIM_CONFIDENCE_SCALE = 1.2
SIM_DECISIVENESS = 0.6
HIST_DAILY_MEAN = 0.0004
HIST_DAILY_VOL = 0.0110
HIST_HORIZON_DAYS = 30
REGIME_SWITCH_PROB = 0.05
REGIME_LOW_VOL = 0.8
REGIME_HIGH_VOL = 1.4

# Backtest window used in the original
YFINANCE_TICKER = "GC=F"
BACKTEST_START_DATE = "2025-02-02"
BACKTEST_END_DATE = "2026-02-02"
