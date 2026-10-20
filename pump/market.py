"""Price/volume access via yfinance, plus StockTwits public endpoints."""
import re
import time
from datetime import timedelta

import pandas as pd
import requests
import yfinance as yf
from yfinance import EquityQuery

from .common import EXCHANGES, MCAP_MAX, MIN_DAY_VOLUME, PRICE_MAX, PRICE_MIN, UNIVERSE_MAX, chunks, now_utc

NY = "America/New_York"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def is_common(sym):
    """Drop warrants, units, rights and preferred/class suffixes (e.g. SEATW, ABCU, XYZ-PA)."""
    if not sym or "-" in sym or "." in sym or "^" in sym:
        return False
    return not (len(sym) >= 5 and (sym.endswith(("W", "U", "R")) or sym.endswith("WS")))


def screen_low_price():
    """Low-price US listed stocks, most active and biggest movers first."""
    q = EquityQuery("and", [
        EquityQuery("is-in", ["exchange", *EXCHANGES]),
        EquityQuery("btwn", ["intradayprice", PRICE_MIN, PRICE_MAX]),
        EquityQuery("gt", ["dayvolume", MIN_DAY_VOLUME]),
        EquityQuery("lt", ["intradaymarketcap", MCAP_MAX]),
    ])
    rows = {}
    for sort, pages in (("dayvolume", 2), ("percentchange", 1)):
        for p in range(pages):
            try:
                res = yf.screen(q, offset=p * 250, size=250, sortField=sort, sortAsc=False)
            except Exception as e:  # keep going with whatever we got
                print(f"screen {sort} page {p} failed: {e}")
                continue
            for x in res.get("quotes", []):
                s = x.get("symbol")
                if is_common(s) and s not in rows:
                    rows[s] = {"ticker": s, "exchange": x.get("exchange"),
                               "mcap": x.get("marketCap"), "name": x.get("shortName")}
    return pd.DataFrame(list(rows.values())[:UNIVERSE_MAX])


def predefined(name, size=100):
    try:
        return [x["symbol"] for x in yf.screen(name, count=size).get("quotes", []) if is_common(x.get("symbol"))]
    except Exception as e:
        print(f"predefined {name} failed: {e}")
        return []


def _download_batch(batch, period, interval, prepost):
    try:
        df = yf.download(batch, period=period, interval=interval, prepost=prepost,
                         group_by="ticker", threads=True, progress=False, auto_adjust=False)
    except Exception as e:
        if len(batch) == 1:
            print(f"download failed for {batch[0]}: {e}")
            return {}
        print(f"download failed for batch of {len(batch)} ({e}); bisecting")
        h = len(batch) // 2
        return {**_download_batch(batch[:h], period, interval, prepost),
                **_download_batch(batch[h:], period, interval, prepost)}
    out = {}
    if df.empty:
        return out
    for t in batch:
        try:
            d = df[t] if isinstance(df.columns, pd.MultiIndex) else df
        except KeyError:
            continue
        d = d.dropna(subset=["Close"])
        if d.empty:
            continue
        idx = d.index.tz_localize("UTC") if d.index.tz is None else d.index
        out[t] = d.set_axis(idx.tz_convert(NY))
    return out


def download(tickers, period, interval, prepost=False):
    """Return {ticker: OHLCV DataFrame indexed in New York time}."""
    tickers = sorted({t for t in tickers if isinstance(t, str) and re.fullmatch(r"[A-Z]{1,5}", t)})
    out = {}
    for batch in chunks(tickers, 200):
        out.update(_download_batch(batch, period, interval, prepost))
        time.sleep(1)
    return out


def session_of(ts):
    m = ts.hour * 60 + ts.minute
    if m < 570:
        return "pre"
    if m < 960:
        return "reg"
    return "post"


def prev_close_and_today(bars, today):
    """Previous regular-session close and today's bars from 5-min data."""
    dates = bars.index.date
    prior = bars[dates < today]
    prior_reg = prior[[session_of(t) == "reg" for t in prior.index]]
    if prior_reg.empty:
        return None, bars[dates == today]
    return float(prior_reg["Close"].iloc[-1]), bars[dates == today]


# ---------------- StockTwits ----------------

class StockTwits:
    BASE = "https://api.stocktwits.com/api/2"

    def __init__(self):
        self.status = "ok"
        self.calls = 0

    def _get(self, path):
        if self.status not in ("ok",):
            return None
        try:
            r = requests.get(f"{self.BASE}/{path}", headers=UA, timeout=15)
            self.calls += 1
        except Exception as e:
            self.status = f"error:{type(e).__name__}"
            return None
        if r.status_code == 429:
            self.status = "rate_limited"
            return None
        if r.status_code == 404:  # unknown symbol on StockTwits; skip it, keep going
            return {}
        if r.status_code != 200:
            self.status = f"http_{r.status_code}"
            return None
        return r.json()

    def trending(self):
        j = self._get("trending/symbols.json")
        if not j:
            return []
        return [{"rank": i + 1, "ticker": s.get("symbol"), "watchlist_count": s.get("watchlist_count")}
                for i, s in enumerate(j.get("symbols", []))]

    def message_rate(self, ticker):
        """Messages/hour over the last hour (extrapolated if the 30-message page is saturated)."""
        j = self._get(f"streams/symbol/{ticker}.json")
        time.sleep(0.6)
        if j is None:
            return None
        msgs = j.get("messages", [])
        if not msgs:
            return {"st_rate": 0.0, "st_bull": None}
        now = now_utc()
        times = [pd.Timestamp(m["created_at"]) for m in msgs]
        last_hour = [t for t in times if now - t <= timedelta(hours=1)]
        if len(last_hour) == len(times) and len(times) >= 5:
            span_h = max((now - min(times)).total_seconds() / 3600, 1 / 60)
            rate = len(times) / span_h
        else:
            rate = float(len(last_hour))
        sent = [((m.get("entities") or {}).get("sentiment") or {}).get("basic") for m in msgs]
        tagged = [s for s in sent if s]
        bull = sum(s == "Bullish" for s in tagged) / len(tagged) if tagged else None
        return {"st_rate": round(rate, 1), "st_bull": None if bull is None else round(bull, 2)}
