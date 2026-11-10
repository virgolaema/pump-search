"""Buy at the close, sell at the next open: does it pay on large US stocks?

Daily bars, adjusted for splits and dividends. Overnight return = open(t) / close(t-1) - 1; intraday = close / open - 1.
Part 1: SPY (the S&P 500 fund) over its whole history, no survivorship problem.
Part 2: today's S&P 500 members over 10 years (survivorship: members that were dropped are missing, which flatters
all returns a little). Every strategy is a daily equal-weight basket; t-statistics are over days, not stock-nights.
Selection rules use only data known at the close. Costs are per round trip (buy at one close, sell at the next open)."""
import io
import os
import time

import numpy as np
import pandas as pd
import requests
import yfinance as yf

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overnight")
LIST_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
COSTS = [0, 1, 2, 5]   # basis points per round trip


def members():
    r = requests.get(LIST_URL, timeout=30)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    return sorted(d["Symbol"].astype(str).str.replace(".", "-", regex=False).unique())


def download(tickers, period):
    O, C = {}, {}
    for i in range(0, len(tickers), 100):
        b = tickers[i:i + 100]
        for attempt in range(3):
            try:
                df = yf.download(b, period=period, interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:
                print(f"batch {i} failed: {e}")
                df = pd.DataFrame()
                time.sleep(5)
        for t in b:
            try:
                d = df[t].dropna(subset=["Open", "Close"])
            except KeyError:
                continue
            if len(d) > 250:
                O[t], C[t] = d["Open"], d["Close"]
        time.sleep(1)
    return pd.DataFrame(O), pd.DataFrame(C)


def line(name, r, per_year=252):
    """r: daily series of basket returns (NaN = no position that day)."""
    x = r.dropna()
    if len(x) < 30:
        return None
    m, s = x.mean(), x.std()
    row = {"strategy": name, "days": len(x), "mean bps": round(m * 1e4, 2), "t": round(m / s * np.sqrt(len(x)), 1),
           "win %": round((x > 0).mean() * 100, 1), "Sharpe": round(m / s * np.sqrt(per_year), 2)}
    full = r.fillna(0)
    for c in COSTS:
        net = full - np.where(r.notna(), c / 1e4, 0)
        yrs = len(full) / per_year
        row[f"%/yr net {c}bp"] = round(((1 + net).prod() ** (1 / yrs) - 1) * 100, 1)
    return row


def md(rows):
    df = pd.DataFrame([r for r in rows if r])
    return ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)] + \
           ["| " + " | ".join(str(v) for v in r) + " |" for r in df.values]


def main():
    L = ["# Buy at the close, sell at the next open", ""]
    # ---------- SPY ----------
    spy = yf.download("SPY", period="max", interval="1d", auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy = spy.dropna(subset=["Open", "Close"])
    on = spy["Open"] / spy["Close"].shift(1) - 1
    idy = spy["Close"] / spy["Open"] - 1
    cc = spy["Close"].pct_change()
    L += [f"## SPY, {spy.index[0].date()} to {spy.index[-1].date()}", ""]
    rows = []
    for lab, sl in [("whole history", slice(None)), ("to 2009", slice(None, "2009-12-31")), ("2010-2019", slice("2010", "2019")),
                    ("2020 to now", slice("2020", None)), ("last 3 years", slice(str(spy.index[-1].year - 3), None))]:
        rows += [line(f"overnight, {lab}", on.loc[sl]), line(f"intraday, {lab}", idy.loc[sl]), line(f"buy and hold, {lab}", cc.loc[sl])]
    L += md(rows) + [""]
    yr = pd.DataFrame({"overnight %": ((1 + on.fillna(0)).groupby(on.index.year).prod() - 1) * 100,
                       "intraday %": ((1 + idy.fillna(0)).groupby(idy.index.year).prod() - 1) * 100}).round(1)
    L += ["By calendar year (no costs): overnight beat intraday in "
          f"{int((yr['overnight %'] > yr['intraday %']).sum())} of {len(yr)} years; overnight was negative in {int((yr['overnight %'] < 0).sum())}.", "",
          "```", yr.tail(12).to_string(), "```", ""]
    dow = on.groupby(on.index.dayofweek).agg(["mean", "std", "count"])
    L += ["Overnight mean by the day of the opening (bps, t): " + ", ".join(
        f"{'Mon Tue Wed Thu Fri'.split()[k]} {v['mean'] * 1e4:+.1f} ({v['mean'] / v['std'] * np.sqrt(v['count']):.1f})" for k, v in dow.iterrows()), ""]

    # ---------- S&P 500 members ----------
    tick = members()
    O, C = download(tick, "10y")
    print(f"members {len(tick)}, with data {O.shape[1]}, days {len(O)}")
    ON = O / C.shift(1) - 1            # overnight return realised at the open of day t
    ID = C / O - 1                     # intraday return of day t
    CC = C.pct_change()
    for X in (ON, ID, CC):
        X[X.abs() > 0.6] = np.nan      # data errors
    prevID, prevCC, prevON = ID.shift(1), CC.shift(1), ON.shift(1)
    basket = lambda mask, minn=5: ON.where(mask).mean(axis=1).where(mask.sum(axis=1) >= minn)
    allm = ON.notna()
    rank = lambda X: X.rank(axis=1, pct=True)
    past_on = ON.shift(1).rolling(60, min_periods=40).mean()        # known at the close of t-1
    past_id = ID.shift(1).rolling(60, min_periods=40).mean()
    S = {
        "all members, every night": basket(allm),
        "all members, intraday (for comparison)": ID.mean(axis=1),
        "after the stock fell 3%+ intraday": basket(prevID <= -0.03),
        "after the stock rose 3%+ intraday": basket(prevID >= 0.03),
        "day's 10% worst intraday performers": basket(rank(prevID) <= 0.10),
        "day's 10% best intraday performers": basket(rank(prevID) >= 0.90),
        "top 10% by own overnight return, past 60 days": basket(rank(past_on) >= 0.90),
        "bottom 10% by own overnight return, past 60 days": basket(rank(past_on) <= 0.10),
        "top 10% overnight AND bottom half intraday, past 60 days": basket((rank(past_on) >= 0.90) & (rank(past_id) <= 0.5)),
        "nights after the index fell 1%+": basket(allm).where(CC.mean(axis=1).shift(1) <= -0.01),
        "nights after the index rose 1%+": basket(allm).where(CC.mean(axis=1).shift(1) >= 0.01),
    }
    L += [f"## Today's S&P 500 members, {O.index[0].date()} to {O.index[-1].date()} ({O.shape[1]} stocks)", "",
          "Equal-weight basket bought at the close and sold at the next open. 'mean bps' is per night held, before costs. "
          "The yearly figures count the nights with no position as zero.", ""] + md([line(k, v) for k, v in S.items()]) + [""]
    mid = O.index[len(O) // 2]
    L += [f"Same strategies, mean bps per night (t) before and after {mid.date()}:", ""]
    for k, v in S.items():
        a, b = v[:mid].dropna(), v[mid:].dropna()
        f = lambda x: f"{x.mean() * 1e4:+.1f} ({x.mean() / x.std() * np.sqrt(len(x)):.1f})" if len(x) > 30 else "n/a"
        L.append(f"- {k}: {f(a)} | {f(b)}")
    per = ON.mean() * 1e4
    L += ["", f"Per stock, mean overnight return over the period: median {per.median():+.1f} bps, 10th to 90th percentile "
              f"{per.quantile(.1):+.1f} to {per.quantile(.9):+.1f} bps; positive for {(per > 0).mean() * 100:.0f}% of stocks. "
              f"Mean intraday: median {(ID.mean() * 1e4).median():+.1f} bps.", ""]
    open(os.path.join(OUT, "results.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
