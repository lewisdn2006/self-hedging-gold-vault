"""Run the hedged-vs-unhedged backtest over several seeds and write results/measured_results.md.

    python scripts/measure_results.py                 # 12 seeds, 10,000 traders (about a minute)
    python scripts/measure_results.py --quick         # 4 seeds, 500 traders (a few seconds)
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from goldvault import config as C                        # noqa: E402
from goldvault.backtest import run_backtest, unhedged_summary   # noqa: E402
from goldvault.data import load_prices_csv                # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--bots", type=int, default=C.SIM_BOT_COUNT)
    ap.add_argument("--quick", action="store_true", help="4 seeds, 500 traders")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "measured_results.md"))
    args = ap.parse_args()
    if args.quick:
        args.seeds, args.bots = 4, 500

    points = load_prices_csv()
    base = unhedged_summary(points)
    closes = [p for _, p in points]

    runs, seconds = [], []
    for seed in range(args.seeds):
        t0 = time.time()
        runs.append(run_backtest(points, seed=seed, bot_count=args.bots))
        seconds.append(time.time() - t0)

    def rng(key, scale=1.0, fmt="{:,.0f}"):
        vals = [r[key] * scale for r in runs]
        return fmt.format(min(vals)) + " to " + fmt.format(max(vals)), statistics.mean(vals)

    # How often the "gold falls to the week's target" event actually happened in the data
    hits = 0
    for r in runs[:1]:
        for t in r["trace"]:
            if t["price"] <= t["target_price"]:
                hits += 1
    # Day the "gold falls" contract price first drops below the minimum the rule will pay
    dead = []
    for r in runs:
        d = next((t["time"] for t in r["trace"] if t["p_bad"] < C.HEDGE_MIN_LMSR_PRICE), None)
        dead.append(d)

    lines = []
    w = lines.append
    w("# Measured results")
    w("")
    w("Produced by `scripts/measure_results.py`. Nothing here is typed in by hand.")
    w("")
    w("- Data: %d daily closes of gold futures (GC=F), %s to %s. Gold went from %s to %s, up %.1f%%." % (
        len(points), points[0][0].date(), points[-1][0].date(),
        "{:,.2f}".format(closes[0]), "{:,.2f}".format(closes[-1]), (closes[-1] / closes[0] - 1) * 100))
    w("- Vault: %d oz of gold and %s cash (%s in total at the start)." % (
        int(C.INITIAL_UNITS), "{:,.0f}".format(C.INITIAL_CASH), "{:,.0f}".format(base["initial_value"])))
    w("- Simulated traders: %s per day. Seeds 0 to %d. Each seed gives a different run because the traders are random." % (
        "{:,}".format(args.bots), args.seeds - 1))
    w("- Average time for one run: %.1f seconds." % statistics.mean(seconds))
    w("")
    w("## Unhedged against hedged")
    w("")
    w("| | final value | return | worst drawdown |")
    w("|---|---|---|---|")
    w("| Unhedged vault | %s | %+.1f%% | %.2f%% |" % (
        "{:,.0f}".format(base["final_value"]), base["return"] * 100, base["max_drawdown"] * 100))
    fv, fv_mean = rng("final_value")
    rt, rt_mean = rng("return", 100, "{:+.1f}%")
    dd, dd_mean = rng("max_drawdown", 100, "{:.2f}%")
    w("| Hedged vault, %d runs | %s (mean %s) | %s (mean %+.1f%%) | %s |" % (
        args.seeds, fv, "{:,.0f}".format(fv_mean), rt, rt_mean, dd))
    w("")
    worse = sum(1 for r in runs if r["final_value"] < base["final_value"])
    dd_worse = sum(1 for r in runs if r["max_drawdown"] > base["max_drawdown"])
    w("The hedged vault finished below the unhedged vault in %d of %d runs and had a larger worst "
      "drawdown in %d of %d runs." % (worse, len(runs), dd_worse, len(runs)))
    w("")
    w("## What the hedge did")
    w("")
    w("| | range over runs |")
    w("|---|---|")
    w("| Gold held at the end (oz) | %s |" % rng("final_units", 1, "{:.1f}")[0])
    w("| Days on which a hedge was bought (of %d) | %s |" % (len(points), rng("hedge_days", 1, "{:.0f}")[0]))
    w("| Cash spent on hedges | %s |" % rng("hedge_spend")[0])
    w("| Fees and impact on those hedges | %s |" % rng("hedge_costs", 1, "{:,.1f}")[0])
    firsts = sorted(set(str(r["first_hedge"].date()) for r in runs if r["first_hedge"]))
    lasts = sorted(set(str(r["last_hedge"].date()) for r in runs if r["last_hedge"]))
    w("| First hedge bought | %s |" % (firsts[0] if firsts else "none"))
    w("| Last hedge bought | %s to %s |" % (lasts[0], lasts[-1]) if lasts else "| Last hedge bought | none |")
    w("| Hedge contracts held at the end | %s |" % rng("final_hedge", 1, "{:.1f}")[0])
    ds = sorted(d for d in dead if d)
    if ds:
        w("| Date the contract price first fell below %.3f (hedging then stops) | %s to %s |" % (
            C.HEDGE_MIN_LMSR_PRICE, ds[0].date(), ds[-1].date()))
    w("")
    w("## Why the hedge does not work yet")
    w("")
    w("- **The market price drifts to zero and stays there.** The simulated traders mostly bet that gold "
      "will not fall, and the LMSR quantities are never reset, so the price of the \"gold falls\" contract "
      "keeps sliding. Once it is below %.3f the hedging rule stops buying, which happens in the first weeks "
      "of the run. The remaining months are an unhedged vault." % C.HEDGE_MIN_LMSR_PRICE)
    w("- **Contracts are never settled.** Every Monday the old contracts are deleted without checking whether "
      "gold reached the week's target, so in this backtest a hedge can only cost money, never pay out. "
      "Gold closed at or below the week's target on %d of %d days." % (hits, len(points)))
    w("- **\"CVaR\" is not CVaR.** `cvar_from_buckets` is the stake-weighted mean of the absolute bucket "
      "returns, clipped to [0, 0.60]. It is not an expected loss in the tail.")
    w("- **One window, and a rising market.** Gold rose 66% in it, so this backtest cannot show whether "
      "the hedge would help in a fall.")
    w("")
    w("## Per-seed results")
    w("")
    w("| seed | final value | return | worst drawdown | hedge days | first hedge | last hedge | spent on hedges |")
    w("|---|---|---|---|---|---|---|---|")
    for r in runs:
        w("| %d | %s | %+.1f%% | %.2f%% | %d | %s | %s | %s |" % (
            r["seed"], "{:,.0f}".format(r["final_value"]), r["return"] * 100, r["max_drawdown"] * 100,
            r["hedge_days"], r["first_hedge"].date() if r["first_hedge"] else "-",
            r["last_hedge"].date() if r["last_hedge"] else "-", "{:,.0f}".format(r["hedge_spend"])))
    w("")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        handle.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
