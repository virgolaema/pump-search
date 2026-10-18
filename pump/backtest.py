"""Blind backtest of volume/price flag rules on ~60 days of 5-min bars.

Rules are chosen on the first 2/3 of trading days (train) and evaluated once on the last 1/3 (test).
Trade model for scoring: buy at the flag bar's close +1% slippage; exit at +30% (take profit),
-15% (stop; also if a bar touches both), or at the last bar of the next trading day."""
import itertools
import os
import sys

import numpy as np
import pandas as pd

from . import market
from .common import ROOT, UNIVERSE, read_csv
from .features import bar_features

OUT = os.path.join(ROOT, "backtest")
TP, SL, SLIP = 0.30, 0.15, 0.01
GRID = {
    "pct_lo": [-5, 0, 5],
    "pct_hi": [15, 25, 40, 60],
    "burst": [3, 5, 10, 20, 50],
    "ret10": [-100, 3, 5, 10],
    "dvol": [25_000, 100_000, 300_000],
}
MAX_PER_DAY = 6       # alerts per day you would actually receive
MIN_TRAIN_FLAGS = 40


def simulate(f, i_list, days):
    """Trade outcome for entries at rows i_list of one ticker's feature frame."""
    out = []
    hi, lo, cl, dt = f["high"].values, f["low"].values, f["close"].values, f["date"].values
    for i in i_list:
        d = dt[i]
        k = days.index(d)
        stop_day = days[min(k + 1, len(days) - 1)]
        entry = cl[i] * (1 + SLIP)
        ret, how = None, "time"
        j = i + 1
        while j < len(cl) and dt[j] <= stop_day:
            if lo[j] <= entry * (1 - SL):
                ret, how = -SL, "stop"; break
            if hi[j] >= entry * (1 + TP):
                ret, how = TP, "tp"; break
            j += 1
        if ret is None:
            ret = cl[min(j, len(cl)) - 1] / entry - 1 if j - 1 > i else 0.0
        win_hi = hi[i + 1:j + 1].max() if j > i + 1 else cl[i]
        out.append((ret, how, win_hi / entry - 1))
    return out


def main():
    u = read_csv(UNIVERSE)
    tickers = list(u["ticker"])
    if "--quick" in sys.argv:
        tickers = tickers[:60]
    bars = market.download(tickers, period="60d", interval="5m", prepost=True)
    print(f"downloaded {len(bars)}/{len(tickers)} tickers")

    cand, events, base_rows = [], [], []
    rng = np.random.default_rng(0)
    for t, b in bars.items():
        f = bar_features(b)
        f = f[(f["tod"] >= 240) & (f["tod"] < 1200)]          # 04:00-20:00 ET, as collected live
        f.index.name = "time"
        f = f.reset_index()
        days = sorted(set(f["date"]))
        if len(days) < 6:
            continue
        # spike events: day high >= +50%; start = first bar with high >= +20%
        for d, g in f.groupby("date"):
            pc = g["prev_close"].iloc[0]
            if not np.isfinite(pc) or pc <= 0:
                continue
            if g["high"].max() >= 1.5 * pc:
                st = g.index[g["high"] >= 1.2 * pc][0]
                events.append({"ticker": t, "date": d, "start_i": st, "start": f.at[st, "time"],
                               "day_high": g["high"].max(), "prev_close": pc,
                               "gain": round((g["high"].max() / pc - 1) * 100)})
        dec = f[(f["tod"] % 10 == 0) & f["burst"].notna() & f["pct"].notna()]
        loose = dec[(dec["pct"] >= min(GRID["pct_lo"])) & (dec["pct"] < max(GRID["pct_hi"])) &
                    (dec["burst"] >= min(GRID["burst"])) & (dec["dvol30"] >= min(GRID["dvol"]))]
        res = simulate(f, list(loose.index), days)
        for (i, r), (ret, how, mx) in zip(loose.iterrows(), res):
            cand.append({"ticker": t, "i": i, "time": r["time"], "date": r["date"], "pct": r["pct"],
                         "burst": r["burst"], "dvol30": r["dvol30"], "ret10": r["ret10"], "close": r["close"],
                         "ret": ret, "how": how, "max_up": mx})
        # baseline: random decision bars in a normal price range with some trading
        pool = dec[(dec["pct"] > -5) & (dec["pct"] < 15) & (dec["dvol30"] >= 25_000)]
        if len(pool):
            pick = pool.sample(min(15, len(pool)), random_state=int(rng.integers(1e9)))
            for (i, r), (ret, how, mx) in zip(pick.iterrows(), simulate(f, list(pick.index), days)):
                base_rows.append({"date": r["date"], "ret": ret, "how": how})

    C, E, B = pd.DataFrame(cand), pd.DataFrame(events), pd.DataFrame(base_rows)
    all_days = sorted(set(C["date"]) | set(B["date"]))
    cut = all_days[int(len(all_days) * 2 / 3)]
    split = lambda df: (df[df["date"] < cut], df[df["date"] >= cut])
    n_train_days = sum(d < cut for d in all_days)
    n_test_days = len(all_days) - n_train_days

    def apply(rule, df):
        m = ((df["pct"] >= rule["pct_lo"]) & (df["pct"] < rule["pct_hi"]) & (df["burst"] >= rule["burst"]) &
             (df["ret10"] >= rule["ret10"]) & (df["dvol30"] >= rule["dvol"]))
        return df[m].sort_values("time").groupby(["ticker", "date"]).head(1)   # first flag per ticker-day

    def stats(fl, ev, ndays):
        s = {"flags": len(fl), "per_day": round(len(fl) / max(ndays, 1), 1)}
        if len(fl):
            s.update(win=round(float((fl["how"] == "tp").mean()) * 100, 1),
                     stop=round(float((fl["how"] == "stop").mean()) * 100, 1),
                     mean_ret=round(float(fl["ret"].mean()) * 100, 2),
                     med_max_up=round(float(fl["max_up"].median()) * 100, 1))
        if len(ev):
            j = ev.merge(fl[["ticker", "date", "time", "close"]], on=["ticker", "date"], how="left")
            early = (j["time"].notna() & (j["time"] < j["start"])).sum()
            tradable = (j["close"].notna() & (j["close"] * (1 + SLIP) * 1.3 <= j["day_high"])).sum()
            s.update(events=len(ev), caught_early=int(early), caught_with_30pct_left=int(tradable))
        return s

    Ctr, Cte = split(C); Etr, Ete = split(E); Btr, Bte = split(B)
    rows = []
    keys = list(GRID)
    for vals in itertools.product(*GRID.values()):
        rule = dict(zip(keys, vals))
        if rule["pct_lo"] >= rule["pct_hi"]:
            continue
        s = stats(apply(rule, Ctr), Etr, n_train_days)
        rows.append({**rule, **s})
    R = pd.DataFrame(rows)
    ok = R[(R["flags"] >= MIN_TRAIN_FLAGS) & (R["per_day"] <= MAX_PER_DAY)].sort_values(
        ["mean_ret", "caught_with_30pct_left", "flags"], ascending=False)
    best = {k: float(v) for k, v in ok.iloc[0][keys].items()}
    test = stats(apply(best, Cte), Ete, n_test_days)
    train = stats(apply(best, Ctr), Etr, n_train_days)
    bstats = lambda df: {"n": len(df), "win": round(float((df["how"] == "tp").mean()) * 100, 1),
                         "mean_ret": round(float(df["ret"].mean()) * 100, 2)} if len(df) else {}

    os.makedirs(OUT, exist_ok=True)
    R.to_csv(os.path.join(OUT, "grid_train.csv"), index=False)
    apply(best, Cte).to_csv(os.path.join(OUT, "flags_test.csv"), index=False)
    E.to_csv(os.path.join(OUT, "events.csv"), index=False)
    L = ["# Backtest (blind split)", "",
         f"Tickers: {len(bars)} (watchlist of {u['date'].iloc[0]}). Days: {len(all_days)} "
         f"({all_days[0]} to {all_days[-1]}); train < {cut} ({n_train_days} d), test >= {cut} ({n_test_days} d).",
         f"Trade model: entry = flag close +1%, exit +30% / -15% / end of next trading day. Break-even win rate ~33%.", "",
         f"**Chosen on train:** {best}", f"- train: {train}", f"- **test: {test}**", "",
         f"Baseline random entries (−5%..+15%, ≥$25k/30min): train {bstats(Btr)}, test {bstats(Bte)}", "",
         "Top 10 rules on train (mean return per trade):", "",
         ok.head(10).to_string(index=False), ""]
    open(os.path.join(OUT, "results.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
