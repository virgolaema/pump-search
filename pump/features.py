"""Per-bar features from 5-min OHLCV (New York time index), shared by live collection and backtest.

Everything at bar i uses only bars <= i (and earlier days), so it is causal."""
import numpy as np
import pandas as pd

BASE_DAYS = 4   # live collection downloads 5 days, i.e. 4 prior days of baseline


def bar_features(b, step=5):
    """step = bar length in minutes (5 for live, 1 for the 1-minute replay)."""
    n30, n10 = 30 // step, 10 // step
    b = b[~b.index.duplicated()].sort_index()
    idx = b.index
    date = pd.Series(idx.date, index=idx)
    tod = pd.Series(idx.hour * 60 + idx.minute, index=idx)
    reg = (tod >= 570) & (tod < 960)

    # previous regular-session close
    last_reg = b["Close"][reg].groupby(date[reg]).last()
    # today has no regular-session bar before 09:30 ET, so reindex over all dates, then shift
    all_days = sorted(set(date))
    prev_by_day = last_reg.reindex(all_days).shift(1).ffill()
    prev_close = date.map(prev_by_day)

    vol30 = b["Volume"].rolling(n30, min_periods=n30).sum()
    # baseline: same clock time (+-10 min) on the previous BASE_DAYS days, median over days
    piv = pd.DataFrame({"d": date.values, "t": tod.values, "v": vol30.values}).pivot_table(
        index="d", columns="t", values="v", aggfunc="first")
    piv = piv.reindex(columns=range(0, 1440, step))
    smooth = piv.T.rolling(2 * n10 + 1, center=True, min_periods=1).mean().T
    base = smooth.shift(1).rolling(BASE_DAYS, min_periods=2).median()
    base_s = pd.Series(base.stack(future_stack=True).reindex(list(zip(date.values, tod.values))).values, index=idx)

    close = b["Close"]
    f = pd.DataFrame({
        "date": date, "tod": tod, "close": close, "high": b["High"], "low": b["Low"],
        "prev_close": prev_close,
        "pct": (close / prev_close - 1) * 100,
        "burst": vol30 / base_s.clip(lower=1.0),
        "dvol30": vol30 * close,
        "ret10": (close / close.shift(n10) - 1) * 100,
        "ret30": (close / close.shift(n30) - 1) * 100,
    }, index=idx)
    return f
