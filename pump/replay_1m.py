"""Does faster data help? Replay the last ~7 days with 1-minute bars and compare four detection set-ups on the
SAME price paths and the SAME rules:
  A  5-min bars, check every 10 min   (what the live system does)
  B  5-min bars, check every 5 min
  C  1-min bars, check every 10 min
  D  1-min bars, check every minute
  D+2  as D, but the order is filled 2 minutes after the flag (a human reacting to a phone alert)
Rules: 'momentum' = the push-alert rule (price +5..+15% on the day, +10% in 10 min, 30-min volume >= 5x the same time
of day on prior days, >= $100k in 30 min); 'tier2' = looser (0..+25%, +5% in 10 min, 3x, $25k).
First flag per ticker-day. Trades: buy the close of the flag minute +1%; sell at +30% or -15% (limit, stop wins ties),
else the close of the same day, -1% on exit. Missing minutes are filled (volume 0, price carried forward)."""
import os

import numpy as np
import pandas as pd

from . import market
from .backtest import OUT
from .common import UNIVERSE, read_csv
from .features import bar_features

RULES = {
    "momentum": dict(lo=5, hi=15, ret10=10, burst=5, dvol=100_000),
    "tier2": dict(lo=0, hi=25, ret10=5, burst=3, dvol=25_000),
}
TP, SL, SLIP = 0.30, 0.15, 0.01


def fill_grid(b, until=None):
    """Reindex to every minute 04:00-19:59 ET on days that have data; carry the price, zero volume.
    until: stop the last day at this timestamp (a day still in progress)."""
    parts = []
    for d, g in b.groupby(b.index.date):
        day0 = pd.Timestamp(d, tz=market.NY)
        end = day0 + pd.Timedelta(hours=19, minutes=59)
        if until is not None and until.date() == d:
            end = min(end, until)
        parts.append(g.reindex(pd.date_range(day0 + pd.Timedelta(hours=4), end, freq="1min")))
    x = pd.concat(parts)
    x["Close"] = x["Close"].ffill()
    for c in ("Open", "High", "Low"):
        x[c] = x[c].fillna(x["Close"])
    x["Volume"] = x["Volume"].fillna(0)
    return x.dropna(subset=["Close"])


def to_5m(x):
    return x.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])


def flags_for(f, rule, cadence, step):
    """Row positions (in the frame f) of the first flag per day. cadence: minutes between checks; bar end time."""
    end_min = f["tod"].values + step
    on = (end_min % cadence == 0) if cadence > step else np.ones(len(f), bool)
    ok = (on & np.isfinite(f["pct"].values) & np.isfinite(f["burst"].values) & np.isfinite(f["ret10"].values)
          & (f["pct"].values >= rule["lo"]) & (f["pct"].values < rule["hi"]) & (f["ret10"].values >= rule["ret10"])
          & (f["burst"].values >= rule["burst"]) & (f["dvol30"].values >= rule["dvol"]))
    idx = np.flatnonzero(ok)
    first = {}
    for i in idx:
        first.setdefault(f["date"].values[i], i)
    return list(first.values())


def sim(x1, k, delay=0):
    """Trade on the 1-min arrays x1, entering at the close of minute k+delay, same-day exits."""
    j = k + delay
    hi, lo, cl, did = x1["high"], x1["low"], x1["close"], x1["dayid"]
    if j >= len(cl) - 1 or did[j] != did[k]:
        return None
    last = int(x1["day_last"][did[j]])
    entry = cl[j] * (1 + SLIP)
    if last <= j:
        return dict(entry=entry, ret=cl[j] * (1 - SLIP) / entry - 1, how="time")
    L, H = lo[j + 1:last + 1], hi[j + 1:last + 1]
    sl_hit, tp_hit = L <= entry * (1 - SL), H >= entry * (1 + TP)
    ks = int(np.argmax(sl_hit)) if sl_hit.any() else len(L)
    kt = int(np.argmax(tp_hit)) if tp_hit.any() else len(L)
    if ks < len(L) and ks <= kt:
        return dict(entry=entry, ret=min(entry * (1 - SL), cl[j + 1 + ks]) * (1 - SLIP) / entry - 1, how="stop")
    if kt < len(L):
        return dict(entry=entry, ret=(1 + TP) * (1 - SLIP) - 1, how="tp")
    return dict(entry=entry, ret=cl[last] * (1 - SLIP) / entry - 1, how="time")


def main():
    tickers = list(read_csv(UNIVERSE)["ticker"])
    bars = market.download(tickers, period="7d", interval="1m", prepost=True)
    print(f"downloaded {len(bars)}/{len(tickers)} tickers")
    arms = {"A 5m bars, every 10 min (live)": (5, 10, 0), "B 5m bars, every 5 min": (5, 5, 0),
            "C 1m bars, every 10 min": (1, 10, 0), "D 1m bars, every minute": (1, 1, 0),
            "D+2 as D, filled 2 min later": (1, 1, 2)}
    trades, events, days_base = [], [], set()
    for t, b in bars.items():
        x = fill_grid(b)
        if len(x) < 2000:
            continue
        f1 = bar_features(x, step=1).reset_index(drop=True)
        did = pd.factorize(f1["date"])[0]
        x1 = {"high": f1["high"].values, "low": f1["low"].values, "close": f1["close"].values, "dayid": did,
              "day_last": np.r_[np.flatnonzero(np.diff(did)), len(did) - 1]}
        days_base |= set(f1.loc[np.isfinite(f1["burst"]) & np.isfinite(f1["pct"]), "date"])
        f5 = bar_features(to_5m(x), step=5).reset_index(drop=True)
        ts1 = x.index                                   # minute timestamps aligned with f1 rows
        ts5 = to_5m(x).index
        # event detection on the 1-min frame
        for d, g in f1.groupby("date"):
            pc = g["prev_close"].iloc[0]
            if np.isfinite(pc) and pc > 0 and g["high"].max() >= 1.5 * pc:
                start = g.index[g["high"] >= 1.2 * pc][0]
                events.append(dict(ticker=t, date=d, start=start, day_high=g["high"].max(), pc=pc))
        for rname, rule in RULES.items():
            for arm, (step, cadence, delay) in arms.items():
                f = f1 if step == 1 else f5
                for i in flags_for(f, rule, cadence, step):
                    # minute index in f1 of the last minute of the flagged bar
                    k = i if step == 1 else int(ts1.get_indexer([ts5[i] + pd.Timedelta(minutes=4)])[0])
                    if k < 0:
                        continue
                    r = sim(x1, k, delay)
                    if r:
                        trades.append(dict(rule=rname, arm=arm, ticker=t, date=f1["date"].values[k], k=k, **r))
    T, E = pd.DataFrame(trades), pd.DataFrame(events)
    os.makedirs(OUT, exist_ok=True)
    T.to_csv(os.path.join(OUT, "replay_1m_trades.csv"), index=False)
    E.to_csv(os.path.join(OUT, "replay_1m_events.csv"), index=False)
    days = sorted(days_base)
    ev = E[E["date"].isin(days)]
    L = ["# 1-minute replay: does faster data help?", "",
         f"{len(bars)} stocks; days with baseline and a previous close: {len(days)} ({days[0]} to {days[-1]}). "
         f"Spikes (day high >= +50% vs previous close) on those days: {len(ev)}. Buy at the flagged minute's close +1%; "
         f"sell +30% / -15% / same-day close, -1% on exit. Small sample: a direction, not a verdict.", ""]
    for rname in RULES:
        L += [f"## Rule: {rname}", "",
              "| set-up | flags | per day | +30% before -15% | -15% first | avg trade | spikes flagged before reaching +20% | of those, with 30%+ still to go |",
              "|---|---|---|---|---|---|---|---|"]
        for arm in arms:
            D = T[(T["rule"] == rname) & (T["arm"] == arm)]
            if D.empty:
                L.append(f"| {arm} | 0 | | | | | | |")
                continue
            caught = left = 0
            for e in ev.itertuples():
                m = D[(D["ticker"] == e.ticker) & (D["date"] == e.date)]
                if len(m) and m["k"].iloc[0] <= e.start:
                    caught += 1
                    left += int(e.day_high >= m["entry"].iloc[0] * 1.3)
            L.append(f"| {arm} | {len(D)} | {len(D) / len(days):.1f} | {(D['how'] == 'tp').mean() * 100:.0f}% | "
                     f"{(D['how'] == 'stop').mean() * 100:.0f}% | {D['ret'].mean() * 100:+.1f}% | {caught} of {len(ev)} | {left} |")
        L.append("")
    open(os.path.join(OUT, "replay_1m.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
