"""Tkinter window for the prediction market:  python -m goldvault.market_demo"""
from __future__ import annotations

from .market_game import MarketGame


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Gold Prediction Market")
    game = MarketGame()
    frame = ttk.Frame(root, padding=12)
    frame.grid(row=0, column=0, sticky="nsew")

    threshold_var = tk.StringVar(value=str(game.threshold))
    liquidity_var = tk.StringVar(value="120")
    cash_var = tk.StringVar(value="100")
    bet_var = tk.StringVar(value="5")
    labels = {name: ttk.Label(frame, text="") for name in ("event", "yes", "no", "cash", "pos")}

    def refresh() -> None:
        p_yes, p_no = game.market.prices()
        labels["event"].config(text=f"Gold price > ${game.threshold:.2f} in 1 week")
        labels["yes"].config(text=f"YES price/prob: {p_yes:.3f}")
        labels["no"].config(text=f"NO price/prob: {p_no:.3f}")
        labels["cash"].config(text=f"Your cash: ${game.cash:.2f}")
        labels["pos"].config(text=f"Your shares: YES {game.shares[0]:.2f} | NO {game.shares[1]:.2f}")

    def start() -> None:
        nonlocal game
        try:
            game = MarketGame(float(liquidity_var.get()), float(cash_var.get()), float(threshold_var.get()))
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        refresh()

    def bet(index: int) -> None:
        try:
            game.place_bet(index, float(bet_var.get()))
        except ValueError as exc:
            messagebox.showerror("Cannot place bet", str(exc))
            return
        refresh()

    def resolve() -> None:
        outcome_yes, payout = game.resolve()
        messagebox.showinfo("Resolved", f"Outcome: {'YES' if outcome_yes else 'NO'}\nPayout: ${payout:.2f}")
        refresh()

    row = 0
    for text, var in (("Gold threshold ($)", threshold_var), ("Liquidity (b)", liquidity_var),
                      ("Starting cash ($)", cash_var), ("Bet amount ($)", bet_var)):
        ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w")
        ttk.Entry(frame, textvariable=var, width=12).grid(row=row, column=1, sticky="w", padx=6)
        row += 1
    ttk.Button(frame, text="Start Market", command=start).grid(row=row, column=0, columnspan=2, sticky="ew")
    for name in ("event", "yes", "no", "cash", "pos"):
        row += 1
        labels[name].grid(row=row, column=0, columnspan=2, sticky="w")
    row += 1
    ttk.Button(frame, text="Buy YES", command=lambda: bet(0)).grid(row=row, column=0, sticky="ew")
    ttk.Button(frame, text="Buy NO", command=lambda: bet(1)).grid(row=row, column=1, sticky="ew")
    ttk.Button(frame, text="Resolve (simulate)", command=resolve).grid(
        row=row + 1, column=0, columnspan=2, sticky="ew")
    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
