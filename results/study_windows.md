# Multi-year test of the weekly-settled hedge

Produced by `scripts/study_windows.py`. Every calendar year of gold futures from 2001 to 2025 is a separate window. In each, the vault starts with gold worth 285,710 and 100,000 cash. Each week a contract pays 1 if the week's last close is at or below a target 5% under the Monday price; contracts are settled each week and the market restarts at 50/50 each Monday; the hedge is sized with the trailing 250-bar 5% CVaR of weekly returns. 3 seeds per window (mean shown), 1,000 simulated traders per day.

Three versions are compared. **Unhedged**: just hold. **Market hedge**: the rule buys from the simulated prediction market. **Oracle**: the same rule and the same costs, but it is told in advance which weeks the event happens; it is an upper bound, not something that can be run live.

| year | gold | unhedged | market hedge | oracle | unhedged worst drawdown | market hedge worst drawdown | premium paid | payouts | event weeks |
|---|---|---|---|---|---|---|---|---|---|
| 2001 | +3.8% | +2.8% | -50.1% | +2.8% | 6.0% | 50.1% | 203,163 | 0 | 0 of 53 |
| 2002 | +24.6% | +18.2% | -30.1% | +34.5% | 5.9% | 33.9% | 192,700 | 13,033 | 1 of 53 |
| 2003 | +20.1% | +14.9% | -41.5% | +57.5% | 11.5% | 43.3% | 241,500 | 34,785 | 2 of 53 |
| 2004 | +3.1% | +2.3% | -49.6% | +2.3% | 9.2% | 49.6% | 194,963 | 0 | 0 of 52 |
| 2005 | +20.6% | +15.3% | -32.4% | +15.3% | 5.2% | 34.2% | 175,593 | 0 | 0 of 52 |
| 2006 | +19.7% | +14.6% | -60.0% | +50.0% | 17.4% | 61.8% | 305,376 | 21,746 | 1 of 52 |
| 2007 | +31.4% | +23.3% | -35.8% | +71.8% | 5.5% | 37.8% | 236,251 | 26,508 | 2 of 53 |
| 2008 | +3.1% | +2.3% | -54.5% | +88.8% | 22.9% | 57.9% | 279,754 | 61,918 | 4 of 53 |
| 2009 | +24.6% | +18.2% | -47.3% | +42.8% | 10.3% | 49.3% | 259,469 | 18,334 | 1 of 53 |
| 2010 | +27.1% | +20.1% | -36.2% | +20.1% | 6.4% | 38.0% | 206,402 | 0 | 0 of 52 |
| 2011 | +10.1% | +7.5% | -44.0% | +47.1% | 14.6% | 44.1% | 237,353 | 31,003 | 2 of 52 |
| 2012 | +4.7% | +3.5% | -49.1% | +3.5% | 10.7% | 51.1% | 202,352 | 0 | 0 of 53 |
| 2013 | -28.8% | -21.3% | -77.8% | +40.1% | 21.8% | 77.8% | 268,626 | 38,026 | 2 of 53 |
| 2014 | -3.4% | -2.5% | -50.0% | -2.5% | 13.1% | 50.4% | 187,738 | 0 | 0 of 53 |
| 2015 | -10.6% | -7.9% | -54.9% | -7.9% | 14.6% | 57.2% | 185,844 | 0 | 0 of 53 |
| 2016 | +7.0% | +5.2% | -44.9% | +5.2% | 13.6% | 48.6% | 203,553 | 0 | 0 of 52 |
| 2017 | +12.6% | +9.3% | -35.3% | +9.3% | 6.1% | 38.1% | 170,610 | 0 | 0 of 52 |
| 2018 | -2.7% | -2.0% | -36.0% | -2.0% | 10.2% | 37.4% | 129,950 | 0 | 0 of 53 |
| 2019 | +18.6% | +13.8% | -30.9% | +13.8% | 4.9% | 32.1% | 170,932 | 0 | 0 of 53 |
| 2020 | +24.3% | +18.0% | -60.9% | +61.4% | 11.3% | 62.3% | 333,898 | 32,708 | 2 of 53 |
| 2021 | -6.1% | -4.5% | -51.7% | +35.6% | 10.5% | 51.8% | 204,612 | 24,205 | 2 of 52 |
| 2022 | +1.4% | +1.1% | -51.0% | +1.1% | 15.4% | 51.6% | 196,229 | 0 | 0 of 52 |
| 2023 | +12.2% | +9.1% | -34.9% | +9.1% | 8.3% | 36.5% | 166,213 | 0 | 0 of 52 |
| 2024 | +27.4% | +20.3% | -29.4% | +20.3% | 6.5% | 29.6% | 190,226 | 0 | 0 of 53 |
| 2025 | +62.6% | +46.4% | -25.2% | +79.8% | 7.5% | 28.3% | 267,488 | 19,332 | 1 of 53 |

## Summary

| | unhedged | market hedge | oracle |
|---|---|---|---|
| Mean yearly return | +9.1% | -44.5% | +28.0% |
| Median yearly return | +9.1% | -44.9% | +20.1% |
| Mean worst drawdown | 10.8% | 46.1% | 10.1% |

- The market hedge beat the unhedged vault on return in 0 of 25 years, had the smaller worst drawdown in 0 of 25, and the smaller weekly 5% CVaR in 0 of 25.
- In the 5 years gold fell (2013, 2014, 2015, 2018, 2021) the market hedge returned -54.1% on average against -7.6% unhedged.

## Why: the price paid against how often the event happens

- The event (a close at or below the target at the end of the week) happened in 20 of 1315 weeks, **1.5%** of the time.
- The hedge paid on average **0.260** per contract (total premium 5,410,796 for 20,830,102 contracts), and each contract paid back 0.015 on average (payouts 321,599).
- A contract is only worth buying below its true chance of paying. Here the price is many times the chance, so the hedge loses money on average whatever the year does.
- Premiums are larger than the vault's cash, so the hedge also sold gold to pay for itself: on average 119.9 oz a year.
- The oracle row shows the hedge itself is not the problem. With the same rule, the same cap and the same costs, knowing which weeks the event happens turns the hedge into a gain.
