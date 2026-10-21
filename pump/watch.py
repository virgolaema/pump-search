"""Minute-by-minute watcher on the short list written by the 10-minute scan (data/hotlist.csv).

Each minute: fetch today's 1-minute bars for the hot tickers, rebuild the features exactly as in the 1-minute
replay (backtest/replay_1m.md, set-up D), and log the first hit per ticker and rule to data/watch_flags.csv.
Push alerts (ntfy + GitHub issue) go out only for the 'momentum' rule and only once per ticker per day.
Nothing is traded. evaluate_day() scores the logged flags after the close."""
import argparse
import os
import time

import numpy as np
import pandas as pd
import yfinance as yf

from . import alerts, market
from .common import ALERTS, HOTLIST, WATCH, WATCH_OUT, append_csv, now_utc, read_csv
from .features import bar_features
from .replay_1m import RULES, SL, SLIP, TP, fill_grid

MAX_TICKERS = 130


def fetch_fresh(tickers):
    """One attempt at today's 1-min bars (no bisecting: a failure just skips this minute)."""
    try:
        df = yf.download(tickers, period="1d", interval="1m", prepost=True, group_by="ticker",
                         threads=True, progress=False, auto_adjust=False)
    except Exception as e:
        print(f"fresh download failed: {type(e).__name__}: {e}")
        return {}
    out = {}
    for t in tickers:
        try:
            d = df[t] if isinstance(df.columns, pd.MultiIndex) else df
        except KeyError:
            continue
        d = d.dropna(subset=["Close"])
        if d.empty:
            continue
        idx = d.index.tz_localize("UTC") if d.index.tz is None else d.index
        out[t] = d.set_axis(idx.tz_convert(market.NY))
    return out


def check(t, prior, fresh_t, today, now_ny):
    """Features of the last complete minute; returns (bar_end_utc, metrics dict) or None."""
    b = fresh_t[(fresh_t.index.date == today) & (fresh_t.index <= now_ny - pd.Timedelta(minutes=1))]
    if b.empty:
        return None
    x = pd.concat([prior, fill_grid(b, until=b.index[-1])])
    f = bar_features(x, step=1)
    r = f.iloc[-1]
    if f.index[-1].date() != today or not np.isfinite([r["pct"], r["burst"], r["ret10"], r["dvol30"]]).all():
        return None
    return (f.index[-1] + pd.Timedelta(minutes=1)).tz_convert("UTC"), dict(
        price=float(r["close"]), pct=float(r["pct"]), ret10=float(r["ret10"]), burst=float(r["burst"]),
        dvol30=float(r["dvol30"]))


def hits(m):
    return [name for name, rule in RULES.items()
            if rule["lo"] <= m["pct"] < rule["hi"] and m["ret10"] >= rule["ret10"] and m["burst"] >= rule["burst"]
            and m["dvol30"] >= rule["dvol"]]


def already_alerted(ticker, day):
    a = read_csv(ALERTS)
    if a.empty:
        return False
    return bool(((a["ticker"] == ticker) & (a["ts"].str[:10] == str(day))).any())


def run(seconds):
    t_end = time.time() + seconds
    hot = read_csv(HOTLIST)
    tickers = [t for t in hot["ticker"] if isinstance(t, str)][:MAX_TICKERS] if not hot.empty else []
    now_ny = pd.Timestamp(now_utc()).tz_convert(market.NY)
    today = now_ny.date()
    if not tickers:
        print("empty hot list")
        time.sleep(max(0, t_end - time.time()))
        return
    raw = market.download(tickers, period="5d", interval="1m", prepost=True)
    prior = {t: fill_grid(b[b.index.date < today]) for t, b in raw.items() if (b.index.date < today).any()}
    wf = read_csv(WATCH)
    seen = set() if wf.empty else set(zip(wf["ticker"], wf["rule"], wf["ts"].str[:10]))
    print(f"watching {len(prior)}/{len(tickers)} tickers for {int(seconds)} s")
    n = 0
    while time.time() < t_end - 8:
        t0 = time.time()
        now_ny = pd.Timestamp(now_utc()).tz_convert(market.NY)
        fresh = fetch_fresh(list(prior))
        new = []
        for t, fr in fresh.items():
            res = check(t, prior[t], fr, today, now_ny)
            if res is None:
                continue
            ts, m = res
            for rule in hits(m):
                key = (t, rule, str(today))
                if key in seen:
                    continue
                seen.add(key)
                new.append(dict(ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"), ticker=t, rule=rule, **{k: round(v, 4) for k, v in m.items()}))
        n += 1
        if new:
            nf = pd.DataFrame(new)
            append_csv(WATCH, nf)
            mom = nf[(nf["rule"] == "momentum") & ~nf["ticker"].map(lambda t: already_alerted(t, today))]
            if not mom.empty:
                mom = mom.assign(reasons=mom.apply(lambda r: f"1-min watcher: {r['ret10']:+.0f}% in 10 min, vol x{r['burst']:.0f}", axis=1))
                print("alerts:", alerts.send(mom[["ts", "ticker", "price", "pct", "reasons"]]))
            print(f"{now_ny:%H:%M} new flags: {[(r['ticker'], r['rule']) for r in new]}")
        time.sleep(max(0, 60 - (time.time() - t0)))
    print(f"watcher done after {n} minutes")


# ---------- scoring after the close ----------

def score(flag, x):
    """Same trade as the replay: buy the flagged minute's close +1%, +30% / -15% / same-day close, -1% exit."""
    ts = pd.Timestamp(flag["ts"]).tz_convert(market.NY)
    day = x[(x.index.date == ts.date()) & (x.index >= ts)]
    entry = flag["price"] * (1 + SLIP)
    if day.empty:
        return dict(how="time", ret=(1 - SLIP) * flag["price"] / entry - 1)
    L, H, C = day["Low"].values, day["High"].values, day["Close"].values
    sl, tp = L <= entry * (1 - SL), H >= entry * (1 + TP)
    ks, kt = (int(np.argmax(sl)) if sl.any() else len(L)), (int(np.argmax(tp)) if tp.any() else len(L))
    if ks < len(L) and ks <= kt:
        return dict(how="stop", ret=min(entry * (1 - SL), C[ks]) * (1 - SLIP) / entry - 1)
    if kt < len(L):
        return dict(how="tp", ret=(1 + TP) * (1 - SLIP) - 1)
    return dict(how="time", ret=C[-1] * (1 - SLIP) / entry - 1)


def evaluate_day(day):
    """Score the day's logged flags (once), append to data/watch_outcomes.csv."""
    wf = read_csv(WATCH)
    if wf.empty:
        return
    wf = wf[wf["ts"].str[:10].isin([str(day), str(day + pd.Timedelta(days=1))])]
    wf = wf[pd.to_datetime(wf["ts"]).dt.tz_convert(market.NY).dt.date == day]
    if wf.empty:
        return
    old = read_csv(WATCH_OUT)
    done = set() if old.empty else set(zip(old["ts"], old["ticker"], old["rule"]))
    wf = wf[[(a, b, c) not in done for a, b, c in zip(wf["ts"], wf["ticker"], wf["rule"])]]
    if wf.empty:
        return
    raw = market.download(sorted(set(wf["ticker"])), period="7d", interval="1m", prepost=True)
    rows = []
    for f in wf.to_dict("records"):
        if f["ticker"] in raw:
            rows.append({**f, **score(f, fill_grid(raw[f["ticker"]]))})
    append_csv(WATCH_OUT, pd.DataFrame(rows))


def report_lines(day, ev):
    wo = read_csv(WATCH_OUT)
    if wo.empty:
        return ["**1-minute watcher:** no flags scored yet.", ""]
    wo["day"] = pd.to_datetime(wo["ts"]).dt.tz_convert(market.NY).dt.date
    out = ["**1-minute watcher** (buy at flag, sell +30% / -15% / same-day close; $100 per trade):"]
    for rule in RULES:
        d, a = wo[(wo["rule"] == rule) & (wo["day"] == day)], wo[wo["rule"] == rule]
        fmt = lambda x: (f"{len(x)} flags, {(x['how'] == 'tp').mean() * 100:.0f}% +30%, {(x['how'] == 'stop').mean() * 100:.0f}% -15%, "
                         f"avg {x['ret'].mean() * 100:+.1f}%, P&L ${100 * x['ret'].sum():+,.0f}") if len(x) else "no flags"
        out.append(f"- {rule}: today {fmt(d)}; all days {fmt(a)}")
    if ev is not None and len(ev):
        wf = read_csv(WATCH)
        n = 0
        for e in ev.itertuples():
            m = wf[(wf["ticker"] == e.ticker) & (pd.to_datetime(wf["ts"]) < pd.Timestamp(e.start))] if not wf.empty else wf
            m = m[pd.to_datetime(m["ts"]).dt.tz_convert(market.NY).dt.date == day] if len(m) else m
            n += int(len(m) > 0)
        out.append(f"- spikes today flagged by the watcher before reaching +20%: {n} of {len(ev)}")
    return out + [""]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=480)
    run(ap.parse_args().seconds)
