"""One collection pass: refresh universe once a day, snapshot price/volume and StockTwits, log flags.

Run every ~30 min during US trading hours (GitHub Actions)."""
import numpy as np
import pandas as pd

from . import alerts, market, watch
from .features import bar_features
from .common import (BURST_MIN, HOTLIST, MAX_PCT_AT_FLAG, MIN_PCT_AT_FLAG, MOM_BURST, MOM_DVOL, MOM_PCT_HI, MOM_PCT_LO,
                     MOM_RET10, PREDICTIONS, PRICE_MAX, REFLAG_HOURS, RUNLOG, RVOL_MIN,
                     SNAPSHOTS, ST_RATE_MIN, ST_RATE_MULT, ST_TRENDING, UNIVERSE, append_csv, now_utc, read_csv)

ST_CANDIDATES = 20  # keeps StockTwits calls ~150/h at a 10-min cadence


def load_universe(today):
    u = read_csv(UNIVERSE)
    if not u.empty and str(u["date"].iloc[0]) == str(today):
        return u
    u = market.screen_low_price()
    if u.empty:
        old = read_csv(UNIVERSE)
        if old.empty:
            raise SystemExit("screener returned nothing and no cached universe")
        print("screener empty, reusing previous universe")
        return old
    daily = market.download(u["ticker"], period="2mo", interval="1d")
    avg = {}
    for t, d in daily.items():
        d = d[d.index.date < today]
        if len(d) >= 5:
            avg[t] = float(d["Volume"].tail(20).mean())
    u["avg_vol20"] = u["ticker"].map(avg)
    u["date"] = str(today)
    u.to_csv(UNIVERSE, index=False)
    print(f"universe rebuilt: {len(u)} tickers")
    return u


def volume_metrics(bars, today, now_ny):
    """Features of the last complete 5-min bar, computed exactly as in the backtest."""
    f = bar_features(bars)
    f = f[f.index <= now_ny - pd.Timedelta(minutes=5)]   # drop the still-forming bar
    if f.empty or f.index[-1].date() != today:
        return None
    r = f.iloc[-1]
    if not np.isfinite(r["prev_close"]):
        return None
    reg_today = f[(f["date"] == today) & (f["tod"] >= 570) & (f["tod"] < 960)]
    return {
        "price": round(float(r["close"]), 4),
        "prev_close": round(float(r["prev_close"]), 4),
        "pct": round(float(r["pct"]), 2),
        "burst": round(float(r["burst"]), 2) if np.isfinite(r["burst"]) else np.nan,
        "ret10": round(float(r["ret10"]), 2) if np.isfinite(r["ret10"]) else np.nan,
        "dollar_vol_30m": round(float(r["dvol30"])) if np.isfinite(r["dvol30"]) else 0,
        "vol_today_reg": float(bars.loc[reg_today.index, "Volume"].sum()),
        "session": market.session_of(now_ny),
    }


def main():
    now = now_utc()
    now_ny = pd.Timestamp(now).tz_convert(market.NY)
    today = now_ny.date()
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    st = market.StockTwits()
    trending = st.trending()
    if trending:
        append_csv(ST_TRENDING, pd.DataFrame(trending).assign(ts=ts))

    u = load_universe(today)
    tickers = list(u["ticker"])
    # add trending StockTwits names that are low-priced (checked below via price)
    extra = [t["ticker"] for t in trending if market.is_common(t["ticker"]) and t["ticker"] not in tickers]
    bars = market.download(tickers + extra, period="5d", interval="5m", prepost=True)

    avg = dict(zip(u["ticker"], u.get("avg_vol20", pd.Series(dtype=float))))
    minutes_in = max(min((now_ny.hour * 60 + now_ny.minute - 570) / 390, 1.0), 0.05)
    rows = []
    for t, b in bars.items():
        m = volume_metrics(b, today, now_ny)
        if m is None:
            continue
        if t in extra and not (m["prev_close"] <= PRICE_MAX):
            continue
        a = avg.get(t)
        m["rvol"] = round(m["vol_today_reg"] / (a * minutes_in), 2) if a and a > 0 and m["session"] != "pre" else np.nan
        m["ticker"] = t
        rows.append(m)
    snap = pd.DataFrame(rows)
    if snap.empty:
        append_csv(RUNLOG, pd.DataFrame([{"ts": ts, "universe": len(tickers), "priced": 0,
                                          "st_status": st.status, "st_calls": st.calls, "flags": 0}]))
        print("no price data")
        return

    # StockTwits message rates for the most interesting names that have not spiked yet
    trend_set = {t["ticker"] for t in trending}
    fresh = snap[(snap["pct"] < MAX_PCT_AT_FLAG) & (snap["pct"] > MIN_PCT_AT_FLAG)]
    cand = list(fresh.sort_values("burst", ascending=False)["ticker"].head(ST_CANDIDATES))
    cand += [t for t in fresh["ticker"] if t in trend_set and t not in cand]
    st_rows = {}
    for t in cand:
        r = st.message_rate(t)
        if r is None:
            break
        st_rows[t] = r
    snap["st_rate"] = snap["ticker"].map(lambda t: st_rows.get(t, {}).get("st_rate", np.nan))
    snap["st_bull"] = snap["ticker"].map(lambda t: st_rows.get(t, {}).get("st_bull", np.nan))
    snap["trending"] = snap["ticker"].isin(trend_set)

    # short list for the minute-by-minute watcher (pump/watch.py): the most actively traded names not yet spiked
    hot = snap[(snap["pct"] > -5) & (snap["pct"] < 40) & (snap["dollar_vol_30m"] >= 10_000)]
    hot = pd.concat([hot.sort_values("dollar_vol_30m", ascending=False).head(100),
                     snap[snap["trending"] & (snap["pct"] < 40)]]).drop_duplicates("ticker").head(130)
    hot[["ticker", "pct", "dollar_vol_30m", "burst"]].to_csv(HOTLIST, index=False)

    # baselines from history
    hist = read_csv(SNAPSHOTS)
    st_base = {}
    if not hist.empty and "st_rate" in hist:
        h = hist[pd.to_datetime(hist["ts"]) < now - pd.Timedelta(hours=3)].dropna(subset=["st_rate"])
        st_base = h.groupby("ticker")["st_rate"].median().to_dict()
    tr_hist = read_csv(ST_TRENDING)
    recently_trending = set()
    if not tr_hist.empty:
        th = tr_hist[(pd.to_datetime(tr_hist["ts"]) < now - pd.Timedelta(minutes=10)) &
                     (pd.to_datetime(tr_hist["ts"]) >= now - pd.Timedelta(hours=24))]
        recently_trending = set(th["ticker"])

    def reasons(r):
        out = []
        pct, burst, ret10 = r["pct"], r["burst"], r["ret10"]
        # v3 momentum rule, chosen by the blind backtest (backtest/results.md)
        if (MOM_PCT_LO <= pct < MOM_PCT_HI and burst >= MOM_BURST and ret10 >= MOM_RET10
                and r["dollar_vol_30m"] >= MOM_DVOL):
            out.append(f"momentum {ret10:+.0f}% in 10 min, vol x{burst:.0f}")
        if not (MIN_PCT_AT_FLAG < pct < MAX_PCT_AT_FLAG):
            return out
        social = []
        rate = r["st_rate"]
        if not np.isnan(rate) and rate >= ST_RATE_MIN:
            b = st_base.get(r["ticker"])
            if (b is None and rate >= 2 * ST_RATE_MIN) or (b is not None and rate >= ST_RATE_MULT * max(b, 1)):
                social.append(f"st_rate {rate:.0f}/h")
        if r["trending"] and r["ticker"] not in recently_trending:
            social.append("st_new_trending")
        if social and not out and burst >= BURST_MIN:
            social.append(f"vol x{burst:.0f}")
        return out + social

    snap["reasons"] = snap.apply(lambda r: "; ".join(reasons(r)), axis=1)
    flagged = snap[snap["reasons"] != ""].copy()

    preds = read_csv(PREDICTIONS)
    if not preds.empty and not flagged.empty:
        recent = preds[pd.to_datetime(preds["ts"]) >= now - pd.Timedelta(hours=REFLAG_HOURS)]
        flagged = flagged[~flagged["ticker"].isin(set(recent["ticker"]))]
    flagged["ts"] = ts
    flagged["score"] = flagged["reasons"].str.count(";") + 1
    strong = flagged[flagged["reasons"].map(alerts.is_strong)]
    if not strong.empty:   # the minute watcher may have alerted already
        strong = strong[~strong["ticker"].map(lambda t: watch.already_alerted(t, today))]
    if not strong.empty:
        print("alerts:", alerts.send(strong))
    append_csv(PREDICTIONS, flagged[["ts", "ticker", "price", "prev_close", "pct", "burst", "rvol",
                                     "st_rate", "st_bull", "trending", "session", "score", "reasons"]])

    keep = snap[(snap["burst"].rank(ascending=False) <= 60) | snap["st_rate"].notna() | snap["trending"]
                | (snap["reasons"] != "")]
    append_csv(SNAPSHOTS, keep.assign(ts=ts)[["ts", "ticker", "price", "pct", "burst", "rvol", "dollar_vol_30m",
                                             "st_rate", "st_bull", "trending", "session"]])
    append_csv(RUNLOG, pd.DataFrame([{"ts": ts, "universe": len(tickers), "priced": len(snap),
                                      "st_status": st.status, "st_calls": st.calls, "flags": len(flagged)}]))
    print(f"{ts}: priced {len(snap)}/{len(tickers) + len(extra)}, stocktwits {st.status} ({st.calls} calls), "
          f"new flags {len(flagged)}: {', '.join(flagged['ticker'])}")


if __name__ == "__main__":
    main()
