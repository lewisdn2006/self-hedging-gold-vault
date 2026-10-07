"""Hedged against unhedged vault on the bundled gold prices:  python examples/run_backtest.py [--seed 0] [--bots 1000]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from goldvault.backtest import run_backtest, unhedged_summary   # noqa: E402
from goldvault.data import load_prices_csv                       # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--bots", type=int, default=1000, help="simulated traders per day (the full size is 10,000)")
args = ap.parse_args()

points = load_prices_csv()
base = unhedged_summary(points)
run = run_backtest(points, seed=args.seed, bot_count=args.bots)
print("unhedged: %12s  %+.1f%%  worst drawdown %.2f%%" % ("{:,.0f}".format(base["final_value"]), base["return"] * 100, base["max_drawdown"] * 100))
print("hedged:   %12s  %+.1f%%  worst drawdown %.2f%%" % ("{:,.0f}".format(run["final_value"]), run["return"] * 100, run["max_drawdown"] * 100))
print("hedge bought on %d of %d days, last on %s" % (run["hedge_days"], run["steps"], run["last_hedge"].date() if run["last_hedge"] else "-"))
