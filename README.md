# Self-Hedging Gold Vault

A gold holding that tries to protect itself. A vault holds gold and cash. Each day a crowd of
simulated traders bets on whether gold will fall to a weekly target price, a prediction market (priced
by the logarithmic market scoring rule, LMSR) turns those bets into a probability, and a rule uses
that probability to buy "gold falls" contracts as insurance for the vault.

The project combines two earlier ones: the vault and its simulated traders (a Streamlit app) and a
stand-alone prediction market (a Tkinter app). They now share one LMSR market, in `goldvault/lmsr.py`.

**The hedge does not work, and this README says so.** Two backtests are included.

- The **original behaviour** (one year, 2025) lost to the unhedged vault in 12 of 12 runs and stopped
  hedging after three weeks ([results](results/measured_results.md)).
- A **corrected version** (`goldvault/weekly.py`) settles its contracts, restarts the market each week and
  uses a real CVaR. Tested on every calendar year from 2001 to 2025 it still lost to simply holding in
  25 of 25 years ([results](results/study_windows.md)). A version of the same rule that is told in advance
  which weeks the event happens makes money, so the loss comes from the price the simulated market
  charges, not from the idea of hedging.

## What it does

- **Prediction market** (`goldvault/lmsr.py`): a two-outcome LMSR market. Buying shares moves the
  price, the cost of a trade is the change in the LMSR cost function, and `delta_for_cost` finds how
  many shares a given amount of money buys.
- **Simulated traders** (`goldvault/traders.py`): 10,000 bots in six groups (risk averse, risk
  neutral, risk seeking, noise, technical, fundamental). Each forms a belief about gold falling to the
  weekly target, picks one of nine return buckets and stakes money in proportion to its confidence.
  The money on the "down" side and the "up" side moves the market each day.
- **Hedging rule** (`goldvault/vault.py`): buys "gold falls" contracts, sized from the gold exposure,
  the traders' confidence and a risk measure, capped at 5% of the gold's value, with a fee of 5 basis
  points and a market-impact cost of 15, and only when the market price is at least 0.005.
- **Backtest, original behaviour** (`goldvault/backtest.py`): runs the vault day by day over a price
  series and reports value, return and worst drawdown against the same vault left alone. Kept as it was
  so that the original results can be reproduced.
- **Backtest, corrected** (`goldvault/weekly.py`): contracts are settled each week, the market restarts
  at 50/50 each Monday, and the hedge is sized with a real CVaR (`goldvault/risk.py`). It can also run an
  "oracle" hedge (told each week's outcome) as an upper bound, and a no-hedge baseline.
- **Apps**: `goldvault/app.py` (Streamlit: replay, hedge rule, event simulation, backtest) and
  `goldvault/market_demo.py` (Tkinter: bet against the prediction market yourself).

## Results

Every number comes from `scripts/measure_results.py` and is in
[results/measured_results.md](results/measured_results.md). Data: 251 daily closes of gold futures
(GC=F), 3 February 2025 to 30 January 2026; gold rose 66.1% (2,857 to 4,745). The vault starts with 100 oz
of gold and 100,000 in cash. Twelve runs, seeds 0 to 11, 10,000 traders.

| | final value | return | worst drawdown |
|---|---|---|---|
| Unhedged | 574,510 | +48.9% | 9.07% |
| Hedged | 554,205 to 566,542 (mean 562,477) | +43.7% to +46.9% (mean +45.8%) | 9.19% to 9.37% |

The hedge cost 2 to 5 points of return and did not reduce the drawdown. A hedge was bought on 14 to 16
of the 251 days, all in February 2025, spending 7,952 to 20,264 in total, of which 16 to 41 was fees and impact.

**Why the original run did not work**

1. *The market price drifts to zero.* The traders mostly bet that gold will not fall, and the
   market quantities are never reset, so the price of the "gold falls" contract slides below the
   rule's 0.005 minimum within about three weeks (24 to 26 February 2025). After that no hedge is bought.
2. *Contracts are never settled.* Each Monday the old contracts are deleted without checking whether
   gold reached the target, so in the backtest a hedge can only lose money.
3. *The "CVaR" is not a CVaR.* It is the stake-weighted mean absolute bucket return, clipped to 0 to 0.60.
4. *One window, rising market.* The test cannot show whether the hedge helps in a fall.

**What the corrected version shows (2001 to 2025, one window per calendar year)**

Each week a contract pays 1 if gold's last close of the week is at or below a target 5% under the Monday
price. Contracts are settled each Friday and the market restarts each Monday. Three versions are compared,
with 3 seeds per year and 1,000 simulated traders a day.

| | unhedged | market hedge | oracle hedge |
|---|---|---|---|
| Mean yearly return | +9.1% | -44.5% | +28.0% |
| Mean worst drawdown | 10.8% | 46.1% | 10.1% |

- The market hedge had a lower return than holding in 25 of 25 years, a larger worst drawdown in 25 of 25
  and a larger weekly 5% CVaR in 25 of 25. In the five years gold fell (2013, 2014, 2015, 2018, 2021) it
  returned -54.1% on average against -7.6% unhedged.
- The event happened in 20 of 1,315 weeks (1.5%). The hedge paid 0.26 per contract on average, and each
  contract paid back 0.015. A contract bought at 0.26 that pays with probability 0.015 loses money
  whichever year it is.
- The oracle hedge, with the same rule, the same cap on spending and the same costs, returned +28.0% on
  average. The hedge mechanism works. What fails is the price: the simulated traders' beliefs are built from the
  gap to the target, not from any information about next week, so the market has no reason to price the event
  at its true 1.5% chance.

**What would fix it, in order** (not done yet): give the traders information about next week's move (a noisy
forecast that is right a little more often than chance); only buy when the market price is below an
estimate of the true chance (a hedge should be bought when it is cheap, not when a rule says to); compare against a
plain rolling put and a trend filter; move the backtest onto the trading-backtester engine.

`goldvault/backtest.py` keeps the original behaviour on purpose. With the
same seed, `run_backtest` gives the same result as the original script (seed 0: 554,205, +43.7%,
drawdown 9.37%, 16 hedge days), and a test checks it.

## How it works

**Each day of the backtest**, in this order: the USD-strength factor takes a random step, the weekly
target is reset on Mondays (the spot price rounded down to a hundred, less 200), old contracts are
cleared on Mondays, the volatility regime may switch, the traders bet, the market moves, and the
hedge rule runs. The order of the random draws is fixed, so a run depends only on its seed.

**The market.** The traders' stakes on the "down" and "up" sides are scaled to 1,000 market shares a
day and added to the two LMSR quantities (b = 2,000). The "gold falls" price is
`exp(q_yes/b) / (exp(q_yes/b) + exp(q_no/b))`. A test compares this with the original formula.

**The rule.** The hedge is `exposure x risk x confidence_scale`, where confidence is the share of
stake on the down side, mapped from [0.1, 0.85] to [0, 1]. No hedge is bought when confidence is outside that
range or the price is below 0.005. Contracts cost the market price plus a 0.01 spread, pay 1 each and are
valued at the market price.

## Running it

```
pip install -r requirements.txt
python examples/run_backtest.py --bots 1000            # one run in about 1 second
python scripts/measure_results.py                      # 12 runs at full size, about a minute; --quick for a few seconds
python scripts/study_windows.py                        # 25 years, market vs oracle vs unhedged, about 2 minutes; --quick is faster
streamlit run goldvault/app.py                         # the vault demo
python -m goldvault.market_demo                        # the prediction market game
```

Prices come from two bundled files in `data/`: the one year used by the original backtest and daily closes
from 30 August 2000 to 6 October 2026 (`goldvault.data.LONG_CSV`). For other dates,
`goldvault.data.fetch_prices_yfinance(start, end)` downloads them.

## Tests

```
python -m pytest
```

Tests cover the CVaR (worst-tail average, fractional weighting, past data only), the weekly backtest
(contracts settle and pay 1 each on an event, the market restarts weekly, cash and gold account for every dollar,
the oracle pays only when events happen), the LMSR (prices sum to 1, a trade costs the change in the cost function, huge quantities do
not overflow), the betting game (cash never goes negative, the winner is drawn in proportion to the price),
the hedge rule (every cap, the fee arithmetic, selling gold for cash), the traders (every bucket, repeatability,
stakes), the backtest (daily accounting, hedges cleared on Mondays, same seed gives the same result), the
data loader, the Streamlit app (run headlessly) and the reproduction of the original reference run.
`python -m pytest -m "not slow"` skips the 6-second reproduction test.

## Limitations

- In the corrected backtest the hedge loses in every year tested, so nothing here supports using it.
- The traders are invented. Their beliefs are built from the same weekly gap to the target that the
  hedge rule uses, so the "market" mostly reflects that gap rather than any information.
- One asset, one year, daily bars, a constant weekly target rule.
- The Streamlit demo uses 2,000 traders per refresh so that it stays quick; the backtest default is 10,000.
- Prices are futures closes, with no roll adjustment.

## Related projects

- [monte-carlo-engine](https://github.com/lewisdn2006/monte-carlo-engine): one GBM simulator for option
  pricing and a pension model.
- [trading-backtester](https://github.com/lewisdn2006/trading-backtester): one cost-aware backtester
  for any trading signal. This project's backtest could be moved onto it.

[CHANGES.md](CHANGES.md) lists what changed from the two original projects.
