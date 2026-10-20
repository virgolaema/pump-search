"""Grid search over flag thresholds, entry trigger and exit levels, with a blind train/test split.

Candidates: every 10-min decision bar that passes a loose filter (price -5..+40% vs previous close, 30-min volume
>= 3x same time of day on prior 4 days, >= $25k/30 min). A rule picks the first candidate per ticker-day.
Entry: at the flag bar, or at the first bar that day at/after the flag with price >= +10/20/30% on the day.
Fills: buy close +1%; exits cost 1%. Take profit and stop are limits on the buy price; stop wins ties, and a stop
that is blown through fills at the bar close. Timeout: close of the same day or of the next trading day.
Train = first 2/3 of days, test = last 1/3 (never used to choose anything)."""
import itertools
import os

import numpy as np
import pandas as pd

from . import market
from .backtest import OUT
from .common import UNIVERSE, read_csv
from .features import bar_features

SLIP_IN, SLIP_OUT = 0.01, 0.01
TPS = np.array([0.10, 0.15, 0.20, 0.30, 0.50, 1.00])
SLS = np.array([0.05, 0.10, 0.15, 0.25, 0.50])
ENTRY = [None, 10.0, 20.0, 30.0]            # None = buy at the flag bar
HORIZ = [0, 1]                              # timeout at close of flag day / next trading day
FLAGS = dict(pct_lo=[-5, 0, 5], pct_hi=[15, 25, 40], burst=[3, 5, 10, 20], ret10=[-100, 0, 5, 10],
             dvol=[25_000, 100_000])
MIN_TRAIN, MIN_TEST = 60, 30


def path_returns(hi, lo, cl, j, e):
    """(len(TPS), len(SLS)) returns for a trade entered at bar j with timeout at bar e."""
    entry = cl[j] * (1 + SLIP_IN)
    s = j + 1
    if e < s:
        return np.full((len(TPS), len(SLS)), cl[j] * (1 - SLIP_OUT) / entry - 1, dtype=np.float32)
    H, L, C = hi[s:e + 1], lo[s:e + 1], cl[s:e + 1]
    m = len(H)
    cmx, cmn = np.maximum.accumulate(H), np.minimum.accumulate(L)
    lt, ls = entry * (1 + TPS), entry * (1 - SLS)
    kt = np.searchsorted(cmx, lt, side="left")[:, None]
    ks = np.searchsorted(-cmn, -ls, side="left")[None, :]
    stop = (ks < m) & (ks <= kt)
    tp = (kt < m) & (kt < ks)
    ret_to = np.full((len(TPS), len(SLS)), C[-1] * (1 - SLIP_OUT) / entry - 1)
    ret_tp = np.broadcast_to(((1 + TPS) * (1 - SLIP_OUT) - 1)[:, None], ret_to.shape)
    fill = np.minimum(ls, C[np.minimum(ks[0], m - 1)])
    ret_st = np.broadcast_to((fill * (1 - SLIP_OUT) / entry - 1)[None, :], ret_to.shape)
    return np.where(stop, ret_st, np.where(tp, ret_tp, ret_to)).astype(np.float32)


def build(bars, gdays):
    gidx = {d: i for i, d in enumerate(gdays)}
    meta, res = [], []
    for ti, (t, b) in enumerate(bars.items()):
        f = bar_features(b)
        f = f[(f["tod"] >= 240) & (f["tod"] < 1200)]
        f = f.reset_index(drop=True)
        n = len(f)
        if n < 500:
            continue
        hi, lo, cl = f["high"].values, f["low"].values, f["close"].values
        pct, r10, bu, dv = f["pct"].values, f["ret10"].values, f["burst"].values, f["dvol30"].values
        gday = np.array([gidx[d] for d in f["date"]])
        ok = (f["tod"].values % 10 == 0) & np.isfinite(pct) & np.isfinite(bu) & np.isfinite(r10) & np.isfinite(dv) \
            & (pct >= -5) & (pct < 40) & (bu >= 3) & (dv >= 25_000)
        cand = np.flatnonzero(ok)
        if not len(cand):
            continue
        ar = np.arange(n)
        nxt = {}
        for x in ENTRY[1:]:
            nxt[x] = np.minimum.accumulate(np.where(pct >= x, ar, n)[::-1])[::-1]
        end = {h: np.searchsorted(gday, np.arange(len(gdays)) + h, side="right") - 1 for h in HORIZ}
        for i in cand:
            R = np.full((len(ENTRY), len(HORIZ), len(TPS), len(SLS)), np.nan, dtype=np.float32)
            cache = {}
            for mi, x in enumerate(ENTRY):
                j = i if x is None else int(nxt[x][i])
                if j >= n or gday[j] != gday[i]:
                    continue
                for hi_, h in enumerate(HORIZ):
                    key = (j, h)
                    if key not in cache:
                        cache[key] = path_returns(hi, lo, cl, j, int(end[h][gday[j]]))
                    R[mi, hi_] = cache[key]
            meta.append((ti, ti * 100000 + gday[i], gday[i], i, pct[i], r10[i], bu[i], dv[i]))
            res.append(R)
    M = pd.DataFrame(meta, columns=["tk", "gid", "day", "i", "pct", "ret10", "burst", "dvol"])
    return M, np.stack(res)


def main():
    tickers = list(read_csv(UNIVERSE)["ticker"])
    bars = market.download(tickers, period="60d", interval="5m", prepost=True)
    gdays = sorted({d for b in bars.values() for d in b.index.date})
    print(f"downloaded {len(bars)}/{len(tickers)} tickers, {len(gdays)} days")
    M, R = build(bars, gdays)
    print(f"candidates: {len(M)}, result array {R.shape}")
    M = M.reset_index(drop=True)
    cut = gdays[int(len(gdays) * 2 / 3)]
    cut_i = gdays.index(cut)
    train = (M["day"] < cut_i).values
    rows = []
    for vals in itertools.product(*FLAGS.values()):
        rule = dict(zip(FLAGS, vals))
        if rule["pct_lo"] >= rule["pct_hi"]:
            continue
        m = ((M["pct"] >= rule["pct_lo"]) & (M["pct"] < rule["pct_hi"]) & (M["burst"] >= rule["burst"]) &
             (M["ret10"] >= rule["ret10"]) & (M["dvol"] >= rule["dvol"])).values
        idx = np.flatnonzero(m)
        if not len(idx):
            continue
        g = M["gid"].values[idx]
        first = idx[np.r_[True, g[1:] != g[:-1]]]
        tr = train[first]
        for mi, x in enumerate(ENTRY):
            Rm = R[first, mi]                                   # (n, H, TP, SL)
            valid = ~np.isnan(Rm[:, 0, 0, 0])
            ntr, nte = int((tr & valid).sum()), int((~tr & valid).sum())
            if ntr < MIN_TRAIN or nte < MIN_TEST:
                continue
            s_tr = np.nansum(Rm[tr & valid], axis=0)           # (H, TP, SL)
            s_te = np.nansum(Rm[~tr & valid], axis=0)
            for hi_, h in enumerate(HORIZ):
                for a, tp in enumerate(TPS):
                    for c, sl in enumerate(SLS):
                        rows.append({**rule, "entry": "flag" if x is None else f"+{x:.0f}%", "horizon": h,
                                     "tp": tp, "sl": sl, "n_train": ntr, "n_test": nte,
                                     "mean_train": s_tr[hi_, a, c] / ntr, "mean_test": s_te[hi_, a, c] / nte})
    G = pd.DataFrame(rows)
    for k in ("train", "test"):
        G[f"pnl_{k}"] = 100 * G[f"mean_{k}"] * G[f"n_{k}"]
    G["both_pos"] = (G["mean_train"] > 0) & (G["mean_test"] > 0)
    os.makedirs(OUT, exist_ok=True)
    G.sort_values("pnl_train", ascending=False).head(3000).to_csv(os.path.join(OUT, "grid_search_top3000.csv"), index=False)

    ntr_days, nte_days = cut_i, len(gdays) - cut_i
    top = G.sort_values("pnl_train", ascending=False).head(12)
    cols = ["pct_lo", "pct_hi", "burst", "ret10", "dvol", "entry", "horizon", "tp", "sl", "n_train", "mean_train",
            "pnl_train", "n_test", "mean_test", "pnl_test"]
    fmt = lambda d: d[cols].round({"mean_train": 4, "mean_test": 4, "pnl_train": 0, "pnl_test": 0}).to_string(index=False)
    best_both = G[G["both_pos"]].assign(minmean=lambda d: d[["mean_train", "mean_test"]].min(axis=1)) \
        .sort_values("minmean", ascending=False).head(8)
    L = ["# Grid search: flag thresholds x entry trigger x take-profit/stop, blind split", "",
         f"{len(bars)} stocks, {len(gdays)} days ({gdays[0]} to {gdays[-1]}); train = first {ntr_days} days, "
         f"test = last {nte_days} days (not used for any choice). $100 per trade, entry +1% / exit -1% slippage.",
         f"Configurations evaluated (>= {MIN_TRAIN} train and >= {MIN_TEST} test trades): {len(G):,}", "",
         f"- positive on train: {(G['mean_train'] > 0).mean() * 100:.1f}%",
         f"- positive on test: {(G['mean_test'] > 0).mean() * 100:.1f}%",
         f"- positive on both: {G['both_pos'].mean() * 100:.1f}%",
         f"- correlation of train and test mean return across configs: {G['mean_train'].corr(G['mean_test']):.2f}",
         f"- median test mean return of the best 100 configs on train: {G.sort_values('pnl_train', ascending=False).head(100)['mean_test'].median() * 100:+.2f}%",
         "", "## Top 12 configs by train P&L (and what they did on the unseen test days)", "", fmt(top), "",
         "## Configs positive on both, ranked by the weaker of the two means", "", fmt(best_both), "",
         "## Average train/test mean return by exit pair (all flag configs, entry at +20%)", ""]
    e = G[G["entry"] == "+20%"]
    L += [e.groupby(["tp", "sl"])[["mean_train", "mean_test"]].mean().round(4).to_string(), ""]
    open(os.path.join(OUT, "grid_search.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
