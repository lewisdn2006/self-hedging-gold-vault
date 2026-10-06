# Self-Hedging Gold Vault

A Streamlit demo of a gold holding that buys its own downside protection from a prediction market. Built solo at the ETH Oxford 2026 hackathon, where it was a finalist.

## The idea

A vault holds gold and cash. Every step it looks at a prediction market on the question "will gold fall below this week's target price?" and uses the market to decide how much protection to buy.

- **Market.** A two-outcome market run by a logarithmic market scoring rule (LMSR) market maker. With `q_yes` and `q_no` shares outstanding and liquidity parameter `b`, the price of the "gold falls" outcome is `exp(q_yes/b) / (exp(q_yes/b) + exp(q_no/b))`.
- **Traders.** 10,000 simulated traders in six profiles (risk-averse, risk-neutral, risk-seeking, noise, technical and fundamental). They form beliefs from the spot price, recent momentum and a simulated dollar-strength factor, then stake money on nine return buckets from "down 10% or more" to "up 10% or more".
- **Hedge sizing.** The hedge scales with the vault's gold exposure, the market's money-weighted confidence, and a risk measure computed from how the traders' stakes are spread across the return buckets. Spending is capped at 5% of the gold exposure per step, and every trade pays a spread, 5 bps in fees and 15 bps in market impact.
- **Weekly cycle.** The target price resets each Monday (spot rounded down to the nearest 100, minus 200) and old hedges expire.

## Running it

```bash
pip install -r requirements.txt
streamlit run main.py
```

The app shows the vault, the simulated market and its bucketed bets, a timeline of portfolio value, and a comparison against holding with no hedge.

**Backtest.** The "Run backtest" button replays one year of daily gold futures prices (`GC=F` from Yahoo Finance, 2 February 2025 to 2 February 2026) through the same logic and lets you download the full trace as a CSV.

## Limitations

- The traders are simulated, not real order flow, so the market price reflects the modelling assumptions above.
- The risk measure is a stake-weighted average of absolute bucket returns. It gauges the expected size of a move. It is not a true Conditional Value at Risk, which would average only the worst tail.
- Volatility regimes and dollar strength are simulated random processes, not market data.
- This is hackathon code: one file and no tests.

## Built with

Python, Streamlit, pandas, yfinance, matplotlib.
