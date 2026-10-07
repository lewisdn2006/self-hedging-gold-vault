# Measured results

Produced by `scripts/measure_results.py`. Nothing here is typed in by hand.

- Data: 251 daily closes of gold futures (GC=F), 2025-02-03 to 2026-01-30. Gold went from 2,857.10 to 4,745.10, up 66.1%.
- Vault: 100 oz of gold and 100,000 cash (385,710 in total at the start).
- Simulated traders: 10,000 per day. Seeds 0 to 11. Each seed gives a different run because the traders are random.
- Average time for one run: 5.2 seconds.

## Unhedged against hedged

| | final value | return | worst drawdown |
|---|---|---|---|
| Unhedged vault | 574,510 | +48.9% | 9.07% |
| Hedged vault, 12 runs | 554,205 to 566,542 (mean 562,477) | +43.7% to +46.9% (mean +45.8%) | 9.19% to 9.37% |

The hedged vault finished below the unhedged vault in 12 of 12 runs and had a larger worst drawdown in 12 of 12 runs.

## What the hedge did

| | range over runs |
|---|---|
| Gold held at the end (oz) | 100.0 to 100.0 |
| Days on which a hedge was bought (of 251) | 14 to 16 |
| Cash spent on hedges | 7,952 to 20,264 |
| Fees and impact on those hedges | 15.9 to 40.5 |
| First hedge bought | 2025-02-03 |
| Last hedge bought | 2025-02-21 to 2025-02-25 |
| Hedge contracts held at the end | 0.0 to 0.0 |
| Date the contract price first fell below 0.005 (hedging then stops) | 2025-02-24 to 2025-02-26 |

## Why the hedge does not work yet

- **The market price drifts to zero and stays there.** The simulated traders mostly bet that gold will not fall, and the LMSR quantities are never reset, so the price of the "gold falls" contract keeps sliding. Once it is below 0.005 the hedging rule stops buying, which happens in the first weeks of the run. The remaining months are an unhedged vault.
- **Contracts are never settled.** Every Monday the old contracts are deleted without checking whether gold reached the week's target, so in this backtest a hedge can only cost money, never pay out. Gold closed at or below the week's target on 2 of 251 days.
- **"CVaR" is not CVaR.** `cvar_from_buckets` is the stake-weighted mean of the absolute bucket returns, clipped to [0, 0.60]. It is not an expected loss in the tail.
- The hedge gives no protection in a rising market and the one run window here is a rising market, so this backtest cannot show whether the hedge would help in a fall.

## Per-seed results

| seed | final value | return | worst drawdown | hedge days | first hedge | last hedge | spent on hedges |
|---|---|---|---|---|---|---|---|
| 0 | 554,205 | +43.7% | 9.37% | 16 | 2025-02-03 | 2025-02-25 | 20,264 |
| 1 | 564,168 | +46.3% | 9.22% | 15 | 2025-02-03 | 2025-02-24 | 10,321 |
| 2 | 566,489 | +46.9% | 9.19% | 14 | 2025-02-03 | 2025-02-21 | 8,005 |
| 3 | 565,458 | +46.6% | 9.21% | 15 | 2025-02-03 | 2025-02-24 | 9,034 |
| 4 | 554,932 | +43.9% | 9.36% | 16 | 2025-02-03 | 2025-02-25 | 19,539 |
| 5 | 566,542 | +46.9% | 9.19% | 14 | 2025-02-03 | 2025-02-21 | 7,952 |
| 6 | 561,115 | +45.5% | 9.27% | 15 | 2025-02-03 | 2025-02-24 | 13,368 |
| 7 | 565,624 | +46.6% | 9.20% | 15 | 2025-02-03 | 2025-02-24 | 8,868 |
| 8 | 565,181 | +46.5% | 9.21% | 15 | 2025-02-03 | 2025-02-24 | 9,311 |
| 9 | 565,479 | +46.6% | 9.21% | 15 | 2025-02-03 | 2025-02-24 | 9,013 |
| 10 | 562,612 | +45.9% | 9.25% | 15 | 2025-02-03 | 2025-02-24 | 11,875 |
| 11 | 557,924 | +44.6% | 9.32% | 15 | 2025-02-03 | 2025-02-24 | 16,553 |
