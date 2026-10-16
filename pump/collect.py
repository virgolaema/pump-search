"""One collection pass: refresh universe once a day, snapshot price/volume and StockTwits, log flags.

Run every ~30 min during US trading hours (GitHub Actions)."""
import numpy as np
import pandas as pd

from . import market
from .common import (BURST_MIN, MAX_PCT_AT_FLAG, MIN_PCT_AT_FLAG, PREDICTIONS, PRICE_MAX, REFLAG_HOURS, RUNLOG, RVOL_MIN,
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
    prev_close, tb = market.prev_close_and_today(bars, today)
    if prev_close is None or tb.empty:
        return None
    sess = market.session_of(now_ny)
    last = float(tb["Close"].iloc[-1])
    # 30-min volume burst vs. median 30-min volume of earlier days in the same session type
    # baseline: 30-min volume ending at the same clock time (+-10 min) on earlier days,
    # so the routine open/close volume surge does not count as a burst
    roll = bars["Volume"].rolling(6, min_periods=6).sum()
    prior = roll[bars.index.date < today].dropna()
    t_last = tb.index[-1].hour * 60 + tb.index[-1].minute
    tod = prior.index.hour * 60 + prior.index.minute
    same = prior[np.abs(tod - t_last) <= 10]
    per_day = same.groupby(same.index.date).mean()
    recent_vol = float(tb["Volume"].tail(6).sum())
    base = float(per_day.median()) if len(per_day) else np.nan
    burst = recent_vol / max(base, 1.0) if not np.isnan(base) else np.nan
    reg_today = tb[[market.session_of(t) == "reg" for t in tb.index]]
    return {
        "price": round(last, 4),
        "prev_close": round(prev_close, 4),
        "pct": round((last / prev_close - 1) * 100, 2),
        "burst": round(burst, 2) if not np.isnan(burst) else np.nan,
        "dollar_vol_30m": round(recent_vol * last),
        "vol_today_reg": float(reg_today["Volume"].sum()),
        "session": sess,
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
        if r["pct"] >= MAX_PCT_AT_FLAG or r["pct"] <= MIN_PCT_AT_FLAG:
            return out
        if (r["burst"] >= BURST_MIN and r["dollar_vol_30m"] >= 50_000 and
                (r["session"] != "reg" or (not np.isnan(r["rvol"]) and r["rvol"] >= RVOL_MIN))):
            out.append(f"vol_burst x{r['burst']:.0f}")
        rate = r["st_rate"]
        if not np.isnan(rate) and rate >= ST_RATE_MIN:
            b = st_base.get(r["ticker"])
            if (b is None and rate >= 2 * ST_RATE_MIN) or (b is not None and rate >= ST_RATE_MULT * max(b, 1)):
                out.append(f"st_rate {rate:.0f}/h")
        if r["trending"] and r["ticker"] not in recently_trending:
            out.append("st_new_trending")
        return out

    snap["reasons"] = snap.apply(lambda r: "; ".join(reasons(r)), axis=1)
    flagged = snap[snap["reasons"] != ""].copy()

    preds = read_csv(PREDICTIONS)
    if not preds.empty and not flagged.empty:
        recent = preds[pd.to_datetime(preds["ts"]) >= now - pd.Timedelta(hours=REFLAG_HOURS)]
        flagged = flagged[~flagged["ticker"].isin(set(recent["ticker"]))]
    flagged["ts"] = ts
    flagged["score"] = flagged["reasons"].str.count(";") + 1
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
