"""What-if: $100 into every tier-2 flag the moment it is up 20% on the day; sell at +50% or -50% from the buy price.

Tier-2 flag (looser than the push alert): price 0..25% vs previous close, +5% in 10 min, 30-min volume >= 3x the
same time of day on the prior 4 days, >= $25k traded in 30 min; first flag per ticker per day, checked every 10 min.
Entry: first 5-min bar at or after the flag, same day, whose close is >= +20% vs the previous close; fill = that
close +1% slippage. Exit: first bar touching +50% (take profit) or -50% (stop; wins ties), else the close of the
next trading day. Control: the same trade for every watchlist stock that crosses +20% (>= $25k/30 min), flagged or not."""
import os
import sys

import numpy as np
import pandas as pd

from . import market
from .common import UNIVERSE, read_csv
from .features import bar_features
from .backtest import OUT

STAKE, SLIP, TP, SL, ENTRY_PCT = 100.0, 0.01, 0.50, 0.50, 20.0


def trade(f, j, days):
    hi, lo, cl, dt = f["high"].values, f["low"].values, f["close"].values, f["date"].values
    entry = cl[j] * (1 + SLIP)
    stop_day = days[min(days.index(dt[j]) + 1, len(days) - 1)]
    k, last = j + 1, j
    while k < len(cl) and dt[k] <= stop_day:
        if lo[k] <= entry * (1 - SL):
            return entry, "stop", -SL
        if hi[k] >= entry * (1 + TP):
            return entry, "tp", TP
        last = k
        k += 1
    return entry, "time", cl[last] / entry - 1


def main():
    tickers = list(read_csv(UNIVERSE)["ticker"])
    bars = market.download(tickers, period="60d", interval="5m", prepost=True)
    print(f"downloaded {len(bars)}/{len(tickers)} tickers")
    rows = []
    for t, b in bars.items():
        f = bar_features(b)
        f = f[(f["tod"] >= 240) & (f["tod"] < 1200)]
        f.index.name = "time"
        f = f.reset_index()
        days = sorted(set(f["date"]))
        if len(days) < 6:
            continue
        dt, pct = f["date"].values, f["pct"].values
        cross = {}   # first bar per day at >= +20% with some liquidity
        for i in np.where((pct >= ENTRY_PCT) & (f["dvol30"].values >= 25_000))[0]:
            cross.setdefault(dt[i], i)
        dec = f[(f["tod"] % 10 == 0) & f["burst"].notna() & f["pct"].notna()]
        tier2 = dec[(dec["pct"] >= 0) & (dec["pct"] < 25) & (dec["ret10"] >= 5) & (dec["burst"] >= 3)
                    & (dec["dvol30"] >= 25_000)]
        flagged = {}
        for i, r in tier2.iterrows():
            flagged.setdefault(r["date"], i)
        for d, i in flagged.items():
            j = next((k for k in range(i, len(f)) if dt[k] != d or pct[k] >= ENTRY_PCT), None)
            if j is None or dt[j] != d or pct[j] < ENTRY_PCT:
                rows.append({"group": "flag_no_entry", "ticker": t, "date": d})
                continue
            if j < len(f) - 1:
                e, how, ret = trade(f, j, days)
                rows.append({"group": "tier2", "ticker": t, "date": d, "entry_time": f.at[j, "time"], "entry": e,
                             "how": how, "ret": ret})
        for d, j in cross.items():
            if j < len(f) - 1:
                e, how, ret = trade(f, j, days)
                rows.append({"group": "control", "ticker": t, "date": d, "entry_time": f.at[j, "time"], "entry": e,
                             "how": how, "ret": ret})
    T = pd.DataFrame(rows)
    all_days = sorted(set(T["date"]))
    cut = all_days[int(len(all_days) * 2 / 3)]
    os.makedirs(OUT, exist_ok=True)
    T.to_csv(os.path.join(OUT, "tier2_trades.csv"), index=False)

    def summ(df, label):
        n = len(df)
        if n == 0:
            return f"| {label} | 0 | | | | | | |"
        pnl = STAKE * df["ret"].sum()
        return (f"| {label} | {n} | {n / max(len(set(df['date'])), 1):.1f} | {(df['how'] == 'tp').mean() * 100:.0f}% | "
                f"{(df['how'] == 'stop').mean() * 100:.0f}% | {(df['how'] == 'time').mean() * 100:.0f}% | "
                f"{df['ret'].mean() * 100:+.1f}% | ${pnl:+,.0f} |")

    L = [f"# Tier-2 what-if: $100 per flag, bought at +20%, sell +50% / -50%", "",
         f"{len(bars)} watchlist stocks, {len(all_days)} trading days ({all_days[0]} to {all_days[-1]}). "
         f"Entry fill = close of the first bar at +20% vs previous close, +1% slippage. Stop wins ties. "
         f"Unfilled exits are closed at the close of the next trading day.", "",
         "| Group | Trades | per day | +50% | -50% | timed out | avg trade | total P&L ($100 each) |",
         "|---|---|---|---|---|---|---|---|"]
    for g, lab in [("tier2", "tier-2 flags"), ("control", "control: every stock at +20%")]:
        d = T[T["group"] == g]
        L += [summ(d, f"{lab} - all days"), summ(d[d["date"] >= cut], f"{lab} - last {len([x for x in all_days if x >= cut])} days")]
    nf = (T["group"] == "flag_no_entry")
    L += ["", f"Tier-2 flags that never reached +20% that day (no trade): {int(nf.sum())}; "
              f"tier-2 trades: {int((T['group'] == 'tier2').sum())}.", ""]
    t2 = T[T["group"] == "tier2"].sort_values("ret")
    if len(t2):
        L += ["Worst 5 / best 5 tier-2 trades (return on the $100):", "",
              t2.head(5)[["ticker", "date", "how", "ret"]].to_string(index=False), "",
              t2.tail(5)[["ticker", "date", "how", "ret"]].to_string(index=False), "",
              "Tier-2 P&L by week:", "",
              t2.assign(week=pd.to_datetime(t2["date"]).dt.to_period("W").astype(str)).groupby("week")["ret"]
                .agg(trades="count", pnl=lambda x: round(STAKE * x.sum())).to_string(), ""]
    open(os.path.join(OUT, "tier2_trade_test.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
