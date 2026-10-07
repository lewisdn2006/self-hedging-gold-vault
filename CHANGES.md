# What changed from the two original projects

This project combines the Streamlit vault (`hackathon/main.py`, 1,025 lines, including a 38-line comment
of results) and the Tkinter prediction market (`predictionmarket.py`, 229 lines). The aim was to combine
them and make the code clean, **not** to redesign the hedge. Behaviour is unchanged unless listed under
"Fixes".

## Combined

- One LMSR market (`BinaryMarket`) is used by the vault, the simulated traders and the betting game. The
  vault used a separate function with the same formula; a test checks they agree.
- The code is split into modules (`lmsr`, `traders`, `vault`, `backtest`, `data`, `market_game`, `app`,
  `market_demo`) with 79 tests. The hedge logic no longer needs Streamlit, so it can be run and tested without it.

## Unchanged on purpose (known weaknesses)

- Contracts are cleared every Monday without settlement.
- The market quantities are never reset, so the price of the "gold falls" contract slides to zero.
- The "CVaR" is the stake-weighted mean absolute bucket return.
- The hedge rule, its parameters and the traders' logic are as they were.

Seed for seed, the backtest gives the same numbers as the original (checked by a test against the
original's seed-0 result).

## Fixes

| Original | Now |
|---|---|
| Randomness came from the global `random` module, so runs could not be repeated and tests could not isolate it. | A `random.Random` object is passed in; the same seed gives the same run. The order of draws is unchanged. |
| `delta_for_cost` returned a number of shares costing slightly more than the amount asked for, so a bet of all your cash could leave negative cash. | Returns the largest number of shares costing no more than the amount. |
| The LMSR price overflowed for large quantities. | Computed relative to the largest quantity; same values otherwise. |
| `run_backtest` could only be run through Streamlit's cached fetchers and the network. | Takes a list of prices. A copy of the prices used is bundled, so results can be repeated offline. |
| The Streamlit app's live mode only fetched 10 days of hourly prices and stopped working when the data ran out. | Defaults to the bundled daily prices; live hourly prices are an option. |
| Modal dialogs and all UI logic in the Tkinter file. | The betting logic is in `MarketGame` and tested; the window is a thin shell. |
| The results of an earlier measurement were pasted into the top of `main.py` as comments. | Moved to `results/measured_results.md`, produced by a script. |
| Constants, bot logic, hedge rule, backtest and UI all in one file. | One module each. |

## Added after the merge: the weekly-settled backtest

`goldvault/weekly.py`, `goldvault/risk.py` and `scripts/study_windows.py` are new. The original backtest is
untouched. The new one:

| Original weakness | Now |
|---|---|
| Contracts deleted each Monday without checking the outcome. | Settled at the week's last close: pay 1 each if at or below the target. |
| Market quantities never reset, so the price slid to zero. | The market restarts at 50/50 every Monday. |
| "CVaR" was the mean absolute bucket return. | `tail_cvar` averages the worst 5% of outcomes. The hedge is sized with the trailing 250-bar 5% CVaR of weekly gold returns. The traders' implied tail CVaR is also available. |
| One rising-market year. | Every calendar year 2001 to 2025, with an oracle upper bound and a no-hedge baseline. |
| Weekly target needed gold at a few thousand dollars. | A percentage target (5% below the Monday price). |

A bug found and fixed while building it: the premium was first measured as the change in cash, which is
wrong when gold is sold to fund a hedge in the same step. The rule now reports its own cost.

Result: the hedge still loses in 25 of 25 years (see the README).
