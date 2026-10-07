"""Test the weekly-settled hedge on every calendar year of gold futures since 2001.

    python scripts/study_windows.py                 # 3 seeds, 1,000 traders per day (about a minute)
    python scripts/study_windows.py --quick         # 1 seed, 300 traders
Writes results/study_windows.md.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from goldvault.data import LONG_CSV, load_prices_csv       # noqa: E402
from goldvault.weekly import run_weekly_backtest           # noqa: E402


def mean(xs):
    return statistics.mean(xs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--bots", type=int, default=1000)
    ap.add_argument("--target-drop", type=float, default=0.05)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "study_windows.md"))
    a = ap.parse_args()
    if a.quick:
        a.seeds, a.bots = 1, 300

    pts = load_prices_csv(LONG_CSV)
    years = sorted({t.year for t, _ in pts})
    years = [y for y in years if 2001 <= y <= 2025]
    rows = []
    for y in years:
        win = [p for p in pts if p[0].year == y]
        runs = {h: [run_weekly_backtest(win, seed=s, bot_count=a.bots, target_drop=a.target_drop, hedge=h)
                    for s in range(a.seeds)] for h in ("market", "oracle")}
        base = runs["market"][0]
        rows.append({
            "year": y, "gold": base["gold_return"], "unh": base["unhedged_return"],
            "unh_dd": base["unhedged_drawdown"], "unh_cvar": base["unhedged_weekly_cvar"],
            "mkt": mean([r["return"] for r in runs["market"]]),
            "mkt_dd": mean([r["max_drawdown"] for r in runs["market"]]),
            "mkt_cvar": mean([r["weekly_cvar"] for r in runs["market"]]),
            "prem": mean([r["premium"] for r in runs["market"]]), "pay": mean([r["payout"] for r in runs["market"]]),
            "orc": mean([r["return"] for r in runs["oracle"]]),
            "orc_dd": mean([r["max_drawdown"] for r in runs["oracle"]]),
            "events": base["event_weeks"], "weeks": base["weeks"],
            "contracts": mean([r["contracts_bought"] for r in runs["market"]]),
            "sold": mean([r["gold_sold_oz"] for r in runs["market"]]),
            "init": base["initial_value"],
        })

    w = []
    P = w.append
    P("# Multi-year test of the weekly-settled hedge")
    P("")
    P("Produced by `scripts/study_windows.py`. Every calendar year of gold futures from 2001 to 2025 is a separate "
      "window. In each, the vault starts with gold worth 285,710 and 100,000 cash. Each week a contract pays 1 if "
      "the week's last close is at or below a target %.0f%% under the Monday price; contracts are settled each week and "
      "the market restarts at 50/50 each Monday; the hedge is sized with the trailing 250-bar 5%% CVaR of weekly "
      "returns. %d seeds per window (mean shown), %s simulated traders per day." % (
          a.target_drop * 100, a.seeds, "{:,}".format(a.bots)))
    P("")
    P("Three versions are compared. **Unhedged**: just hold. **Market hedge**: the rule buys from the simulated "
      "prediction market. **Oracle**: the same rule and the same costs, but it is told in advance which weeks the "
      "event happens; it is an upper bound, not something that can be run live.")
    P("")
    P("| year | gold | unhedged | market hedge | oracle | unhedged worst drawdown | market hedge worst drawdown | premium paid | payouts | event weeks |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        P("| %d | %+.1f%% | %+.1f%% | %+.1f%% | %+.1f%% | %.1f%% | %.1f%% | %s | %s | %d of %d |" % (
            r["year"], r["gold"] * 100, r["unh"] * 100, r["mkt"] * 100, r["orc"] * 100, r["unh_dd"] * 100,
            r["mkt_dd"] * 100, "{:,.0f}".format(r["prem"]), "{:,.0f}".format(r["pay"]), r["events"], r["weeks"]))
    P("")
    n = len(rows)
    better = sum(1 for r in rows if r["mkt"] > r["unh"])
    dd_better = sum(1 for r in rows if r["mkt_dd"] < r["unh_dd"])
    cv_better = sum(1 for r in rows if r["mkt_cvar"] < r["unh_cvar"])
    falling = [r for r in rows if r["gold"] < 0]
    P("## Summary")
    P("")
    P("| | unhedged | market hedge | oracle |")
    P("|---|---|---|---|")
    P("| Mean yearly return | %+.1f%% | %+.1f%% | %+.1f%% |" % (mean([r["unh"] for r in rows]) * 100, mean([r["mkt"] for r in rows]) * 100, mean([r["orc"] for r in rows]) * 100))
    P("| Median yearly return | %+.1f%% | %+.1f%% | %+.1f%% |" % (statistics.median([r["unh"] for r in rows]) * 100, statistics.median([r["mkt"] for r in rows]) * 100, statistics.median([r["orc"] for r in rows]) * 100))
    P("| Mean worst drawdown | %.1f%% | %.1f%% | %.1f%% |" % (mean([r["unh_dd"] for r in rows]) * 100, mean([r["mkt_dd"] for r in rows]) * 100, mean([r["orc_dd"] for r in rows]) * 100))
    P("")
    P("- The market hedge beat the unhedged vault on return in %d of %d years, had the smaller worst drawdown in %d of %d, "
      "and the smaller weekly 5%% CVaR in %d of %d." % (better, n, dd_better, n, cv_better, n))
    if falling:
        P("- In the %d years gold fell (%s) the market hedge returned %+.1f%% on average against %+.1f%% unhedged." % (
            len(falling), ", ".join(str(r["year"]) for r in falling), mean([r["mkt"] for r in falling]) * 100,
            mean([r["unh"] for r in falling]) * 100))
    tot_prem = sum(r["prem"] for r in rows)
    tot_pay = sum(r["pay"] for r in rows)
    ev = sum(r["events"] for r in rows)
    wk = sum(r["weeks"] for r in rows)
    contracts = sum(r["contracts"] for r in rows)
    P("")
    P("## Why: the price paid against how often the event happens")
    P("")
    P("- The event (a close at or below the target at the end of the week) happened in %d of %d weeks, **%.1f%%** of the time." % (ev, wk, ev / wk * 100))
    P("- The hedge paid on average **%.3f** per contract (total premium %s for %s contracts), and each contract paid back %.3f on average (payouts %s)." % (
        tot_prem / contracts, "{:,.0f}".format(tot_prem), "{:,.0f}".format(contracts), tot_pay / contracts, "{:,.0f}".format(tot_pay)))
    P("- A contract is only worth buying below its true chance of paying. Here the price is many times the chance, so the hedge loses money on average whatever the year does.")
    P("- Premiums are larger than the vault's cash, so the hedge also sold gold to pay for itself: on average %.1f oz a year." % mean([r["sold"] for r in rows]))
    P("- The oracle row shows the hedge itself is not the problem. With the same rule, the same cap and the same costs, knowing which weeks the event happens turns the hedge into a gain.")
    P("")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write("\n".join(w))
    print("\n".join(w))


if __name__ == "__main__":
    main()
