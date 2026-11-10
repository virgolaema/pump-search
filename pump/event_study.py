"""Event study on the live flags: what does the price do after a flag, independent of any exit rule?

For every live flag (10-minute scan since 2026-10-19 by category, minute watcher by rule) the 5-minute price path
after the flag is measured against the flag price: +10, +30, +60, +120 minutes, the regular close (16:00 ET), the end
of the extended session, the next day's open and close, plus the best and worst price reached the same day.
No slippage or fees are applied here (a real round trip costs roughly 2% on these stocks).
Control: for each flag, 10 random watchlist stocks that traded in the previous 30 minutes, same times, same horizons.
Also describes the spikes themselves (data/events.csv): time to peak and how much is kept by the close."""
import os

import numpy as np
import pandas as pd

from . import market
from .backtest import OUT
from .common import EVENTS, PREDICTIONS, UNIVERSE, WATCH, read_csv
from .flag_trades import V3_START, category

HORIZ = [10, 30, 60, 120]
COLS = [f"r{h}" for h in HORIZ] + ["r_close", "r_end", "r_next_open", "r_next_close", "mfe", "mae"]
N_CONTROL = 10
MIN = 60 * 10 ** 9


def prep(b):
    b = b[~b.index.duplicated()].sort_index()
    tod = b.index.hour * 60 + b.index.minute
    b = b[(tod >= 240) & (tod < 1200)]
    if b.empty:
        return None
    day = np.array([d.toordinal() for d in b.index.date])
    return dict(t=b.index.tz_convert("UTC").as_unit("ns").asi8, day=day, tod=(b.index.hour * 60 + b.index.minute).values,
                o=b["Open"].values, h=b["High"].values, l=b["Low"].values, c=b["Close"].values)


def path(a, t0, price):
    """Returns after time t0 (UTC ns) relative to price, using bars that start at or after t0."""
    i0 = int(np.searchsorted(a["t"], t0, side="left"))
    d = pd.Timestamp(t0, tz="UTC").tz_convert(market.NY).date().toordinal()
    same = np.flatnonzero(a["day"] == d)
    same = same[same >= i0]
    out = {}
    last_c = lambda idx: a["c"][idx[-1]] / price - 1 if len(idx) else 0.0
    for h in HORIZ:
        out[f"r{h}"] = last_c(same[a["t"][same] + 5 * MIN <= t0 + h * MIN])
    reg = same[a["tod"][same] < 960]
    t0_tod = pd.Timestamp(t0, tz="UTC").tz_convert(market.NY)
    out["r_close"] = last_c(reg) if t0_tod.hour * 60 + t0_tod.minute < 955 else np.nan
    out["r_end"] = last_c(same)
    out["mfe"] = a["h"][same].max() / price - 1 if len(same) else 0.0
    out["mae"] = a["l"][same].min() / price - 1 if len(same) else 0.0
    out["t_peak_min"] = (a["t"][same[np.argmax(a["h"][same])]] - t0) / MIN if len(same) else np.nan
    later = np.unique(a["day"][a["day"] > d])
    out["r_next_open"] = out["r_next_close"] = np.nan
    if len(later):
        nxt = np.flatnonzero((a["day"] == later[0]) & (a["tod"] >= 570) & (a["tod"] < 960))
        if len(nxt):
            out["r_next_open"] = a["o"][nxt[0]] / price - 1
            out["r_next_close"] = a["c"][nxt[-1]] / price - 1
    return out


def table(D, by):
    rows = []
    for key, g in D.groupby(by, sort=False):
        r = {"group": key, "n": len(g)}
        for c in COLS:
            x = g[c].dropna()
            r[c] = f"{x.mean() * 100:+.1f} ± {x.std() / np.sqrt(len(x)) * 100:.1f}" if len(x) > 1 else "n/a"
        rows.append(r)
    return pd.DataFrame(rows)


def md(df):
    return ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)] + \
           ["| " + " | ".join(str(v) for v in r) + " |" for r in df.values]


def main():
    p = read_csv(PREDICTIONS)
    p = p[p["ts"] >= V3_START].copy()
    p["channel"] = "scan: " + p["reasons"].map(category).fillna("other")
    w = read_csv(WATCH)
    w["channel"] = "watcher: " + w["rule"]
    flags = pd.concat([p[["ts", "ticker", "price", "channel"]], w[["ts", "ticker", "price", "channel"]]], ignore_index=True)
    ev = read_csv(EVENTS)
    uni = list(read_csv(UNIVERSE)["ticker"])
    tickers = sorted(set(uni) | set(flags["ticker"]) | set(ev["ticker"]))
    bars = market.download(tickers, period="60d", interval="5m", prepost=True)
    A = {t: a for t, a in ((t, prep(b)) for t, b in bars.items()) if a is not None}
    print(f"downloaded {len(A)}/{len(tickers)} tickers; flags {len(flags)}, spikes {len(ev)}")

    rng = np.random.default_rng(0)
    pool = [t for t in uni if t in A]
    rows, ctrl = [], []
    for f in flags.itertuples():
        ts = pd.Timestamp(f.ts).as_unit("ns")
        t0 = ts.floor("5min").value if f.channel.startswith("scan") else ts.ceil("5min").value
        if f.ticker not in A:
            continue
        rows.append({"ts": f.ts, "ticker": f.ticker, "channel": f.channel, "price": f.price, **path(A[f.ticker], t0, f.price)})
        got = 0
        for c in rng.permutation(pool):
            if c == f.ticker:
                continue
            a = A[c]
            i = int(np.searchsorted(a["t"], t0, side="left"))
            if i == 0 or t0 - a["t"][i - 1] > 35 * MIN:
                continue
            ctrl.append({"channel": f.channel, **path(a, t0, a["c"][i - 1])})
            got += 1
            if got == N_CONTROL:
                break
    F, C = pd.DataFrame(rows), pd.DataFrame(ctrl)
    ny = pd.to_datetime(F["ts"], utc=True).dt.tz_convert(market.NY)
    F["day"], F["tod"] = ny.dt.date, ny.dt.hour * 60 + ny.dt.minute
    os.makedirs(OUT, exist_ok=True)
    F.to_csv(os.path.join(OUT, "event_study_flags.csv"), index=False)

    S = []
    for e in ev.itertuples():
        if e.ticker not in A:
            continue
        a, t0 = A[e.ticker], pd.Timestamp(e.start).as_unit("ns").value
        i = int(np.searchsorted(a["t"], t0, side="left"))
        if i >= len(a["t"]) or a["t"][i] != t0:
            continue
        r = path(a, t0 + 5 * MIN, a["c"][i])
        S.append({"date": e.date, "ticker": e.ticker, "start": e.start, "entry": a["c"][i], "day_gain": e.max_gain,
                  "entry_vs_prev_close": a["c"][i] / e.prev_close - 1, **r})
    S = pd.DataFrame(S)
    S.to_csv(os.path.join(OUT, "event_study_spikes.csv"), index=False)

    days = sorted(F["day"].unique())
    L = ["# Event study: price after a live flag", "",
         f"{len(F)} live flags on {len(days)} trading days ({days[0]} to {days[-1]}). Mean return ± standard error in %, measured "
         f"from the flag price on 5-minute bars, no slippage or fees. r10..r120 = minutes after the flag; r_close = 16:00 ET; "
         f"r_end = end of the extended session; mfe / mae = best / worst price reached the same day.", "",
         "## Flags", ""] + md(table(F, "channel")) + ["", "## Control: random watchlist stocks at the same moments", ""] + \
        md(table(C, "channel")) + [""]
    mid = days[len(days) // 2]
    F["half"] = np.where(F["day"] < mid, "first half of days", "second half of days")
    L += ["## Flags, first and second half of the period", ""]
    for ch, g in F.groupby("channel", sort=False):
        t = table(g, "half")
        t["group"] = ch + " — " + t["group"]
        L += md(t) + [""]
    if len(S):
        st = pd.to_datetime(S["start"], utc=True).dt.tz_convert(market.NY)
        S["when"] = np.where(st.dt.hour * 60 + st.dt.minute < 570, "starts pre-market",
                             np.where(st.dt.hour * 60 + st.dt.minute < 960, "starts in regular hours", "starts post-market"))
        L += ["## The spikes themselves (day high ≥ +50%): buying the close of the first 5-minute bar at +20%", "",
              f"{len(S)} spikes. Median price at that bar's close: {S['entry_vs_prev_close'].median() * 100:+.0f}% vs the previous close. "
              f"Median time from there to the day's high: {S['t_peak_min'].median():.0f} minutes. "
              f"Share still above the entry at the end of the day: {(S['r_end'] > 0).mean() * 100:.0f}%; "
              f"at the next day's close: {(S['r_next_close'].dropna() > 0).mean() * 100:.0f}%.", ""] + md(table(S, "when")) + [""]
    open(os.path.join(OUT, "event_study.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
