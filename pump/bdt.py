"""Boosted decision tree on 60 days of 5-min bars: what precedes a gain, and does it make money out of sample?

Examples: every 10-min decision point (price -5..+25% vs previous close, >= $10k traded in 30 min, a baseline for
volume available). Label: buying that bar's close (+1% slippage) reaches +30% before -15% by the end of the same
day (the same trade as in the other tests). All features use only data available at the decision time:
  intraday  pct, ret10, ret30, burst, dvol30, range30, run_high_pct, from_high, active1h, rel_vol_today, tod, dow
  history   prev_ret, prev_range, max_gain_5, n_spike30_20, days_since_50, dist_high20, dist_low20, avg20_dvol
  stock     logprice, mcap_est (shares from the universe market cap / price at build time, times the current price)
Split by date: first 2/3 of days train (hyper-parameters picked on its last quarter), last 1/3 test, used once."""
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score

from . import market
from .backtest import OUT
from .common import UNIVERSE, read_csv
from .features import bar_features

TP, SL, SLIP = 0.30, 0.15, 0.01
FEATS = ["pct", "ret10", "ret30", "burst", "logdvol30", "range30", "run_high_pct", "from_high", "active1h",
         "rel_vol_today", "tod", "dow", "prev_ret", "prev_range", "max_gain_5", "n_spike30_20", "days_since_50",
         "dist_high20", "dist_low20", "logavg20_dvol", "logprice", "logmcap"]


def day_features(f):
    g = f.groupby("date")
    D = pd.DataFrame({"hi": g["high"].max(), "lo": g["low"].min(), "vol": g["vol"].sum(), "pc": g["prev_close"].first(),
                      "close": g["close"].last()})
    D["dvol"] = (f["close"] * f["vol"]).groupby(f["date"]).sum()
    D["gain_hi"] = D["hi"] / D["pc"] - 1
    s50 = (D["gain_hi"] >= 0.5).values
    since, last = np.full(len(D), 60.0), None
    for i in range(len(D)):
        if last is not None:
            since[i] = min(i - last, 60)
        if s50[i]:
            last = i
    X = pd.DataFrame(index=D.index)
    X["prev_ret"] = D["close"].shift(1) / D["close"].shift(2) - 1
    X["prev_range"] = ((D["hi"] - D["lo"]) / D["close"]).shift(1)
    X["max_gain_5"] = D["gain_hi"].shift(1).rolling(5, min_periods=2).max()
    X["n_spike30_20"] = (D["gain_hi"] >= 0.3).astype(float).shift(1).rolling(20, min_periods=3).sum()
    X["days_since_50"] = since
    X["avg20_vol"] = D["vol"].shift(1).rolling(20, min_periods=3).mean()
    X["avg20_dvol"] = D["dvol"].shift(1).rolling(20, min_periods=3).mean()
    X["high20"] = D["hi"].shift(1).rolling(20, min_periods=3).max()
    X["low20"] = D["lo"].shift(1).rolling(20, min_periods=3).min()
    return X


def label(hi, lo, cl, i, last):
    entry = cl[i] * (1 + SLIP)
    if last <= i:
        return 0, cl[i] * (1 - SLIP) / entry - 1, 0.0
    L, H = lo[i + 1:last + 1], hi[i + 1:last + 1]
    sl, tp = L <= entry * (1 - SL), H >= entry * (1 + TP)
    ks, kt = (int(np.argmax(sl)) if sl.any() else len(L)), (int(np.argmax(tp)) if tp.any() else len(L))
    mx = H.max() / cl[i] - 1
    if ks < len(L) and ks <= kt:
        return 0, min(entry * (1 - SL), cl[i + 1 + ks]) * (1 - SLIP) / entry - 1, mx
    if kt < len(L):
        return 1, (1 + TP) * (1 - SLIP) - 1, mx
    return 0, cl[last] * (1 - SLIP) / entry - 1, mx


def build_examples(t, b, shares):
    bb = b[~b.index.duplicated()].sort_index()
    f = bar_features(bb)
    f["vol"], f["open"] = bb["Volume"].values, bb["Open"].values
    f = f[(f["tod"] >= 240) & (f["tod"] < 1200)]
    f.index.name = "time"
    f = f.reset_index()
    if len(f) < 800:
        return None
    X = day_features(f)
    for c in X.columns:
        f[c] = f["date"].map(X[c])
    g = f.groupby("date")
    f["run_high"] = g["high"].cummax()
    f["run_high_pct"] = (f["run_high"] / f["prev_close"] - 1) * 100
    f["from_high"] = (f["close"] / f["run_high"] - 1) * 100
    f["rel_vol_today"] = g["vol"].cumsum() / f["avg20_vol"].where(f["avg20_vol"] > 0)
    f["range30"] = (f["high"].rolling(6).max() - f["low"].rolling(6).min()) / f["close"] * 100
    f["active1h"] = pd.Series(1.0, index=pd.DatetimeIndex(f["time"])).rolling("60min").count().values
    f["dow"] = pd.to_datetime(f["date"]).dt.dayofweek
    f["dist_high20"] = f["close"] / f["high20"] - 1
    f["dist_low20"] = f["close"] / f["low20"] - 1
    f["logdvol30"] = np.log10(f["dvol30"] + 1)
    f["logavg20_dvol"] = np.log10(f["avg20_dvol"] + 1)
    f["logprice"] = np.log10(f["close"])
    f["logmcap"] = np.log10(shares * f["close"]) if shares else np.nan
    ok = (((f["tod"] + 5) % 10 == 0) & (f["tod"] < 1195) & np.isfinite(f[["pct", "burst", "ret10", "dvol30"]]).all(axis=1)
          & (f["pct"] >= -5) & (f["pct"] < 25) & (f["dvol30"] >= 10_000) & f["avg20_vol"].notna())
    rows = np.flatnonzero(ok.values)
    if not len(rows):
        return None
    did = pd.factorize(f["date"])[0]
    day_last = np.r_[np.flatnonzero(np.diff(did)), len(did) - 1]
    hi, lo, cl = f["high"].values, f["low"].values, f["close"].values
    lab = [label(hi, lo, cl, i, int(day_last[did[i]])) for i in rows]
    E = f.iloc[rows].copy()
    E["ticker"] = t
    E["y"], E["ret"], E["maxfwd"] = zip(*lab)
    return E[["ticker", "time", "date", "dvol30", "burst", "pct", "ret10"] + [c for c in FEATS if c not in ("burst", "pct", "ret10")] + ["y", "ret", "maxfwd"]]


def first_per_day(E, mask):
    d = E[mask].sort_values("time")
    return d.groupby(["ticker", "date"]).head(1)


def summary(d, n_days):
    if d.empty:
        return "no alerts"
    return (f"{len(d)} alerts ({len(d) / n_days:.1f}/day), +30% before -15%: {d['y'].mean() * 100:.0f}%, "
            f"avg trade {d['ret'].mean() * 100:+.1f}%, P&L at $100 each ${100 * d['ret'].sum():+,.0f}")


def main():
    u = read_csv(UNIVERSE)
    tickers = list(u["ticker"])
    mcap = dict(zip(u["ticker"], u["mcap"]))
    udate = pd.Timestamp(str(u["date"].iloc[0])).date()
    bars = market.download(tickers, period="60d", interval="5m", prepost=True)
    print(f"downloaded {len(bars)}/{len(tickers)} tickers")
    parts = []
    for t, b in bars.items():
        reg = b[(b.index.hour * 60 + b.index.minute >= 570) & (b.index.hour * 60 + b.index.minute < 960) & (b.index.date < udate)]
        shares = (mcap.get(t) / reg["Close"].iloc[-1]) if len(reg) and mcap.get(t) and np.isfinite(mcap.get(t)) else None
        E = build_examples(t, b, shares)
        if E is not None:
            parts.append(E)
    E = pd.concat(parts, ignore_index=True)
    E["ret"] = E["ret"].astype(float)
    days = sorted(E["date"].unique())
    cut = days[int(len(days) * 2 / 3)]
    tr, te = E[E["date"] < cut], E[E["date"] >= cut]
    n_tr_days, n_te_days = len(set(tr["date"])), len(set(te["date"]))
    print(f"examples {len(E):,}; train {len(tr):,} ({n_tr_days} d), test {len(te):,} ({n_te_days} d); base rate "
          f"{tr['y'].mean() * 100:.2f}% / {te['y'].mean() * 100:.2f}%")

    # hyper-parameters on the last quarter of the training days
    tdays = sorted(set(tr["date"]))
    vcut = tdays[int(len(tdays) * 0.75)]
    a, v = tr[tr["date"] < vcut], tr[tr["date"] >= vcut]
    best, best_ap = None, -1
    for depth in (2, 3, 4):
        for iters in (100, 300):
            m = HistGradientBoostingClassifier(max_depth=depth, max_iter=iters, learning_rate=0.05, min_samples_leaf=200,
                                               l2_regularization=1.0, random_state=0).fit(a[FEATS], a["y"])
            ap = average_precision_score(v["y"], m.predict_proba(v[FEATS])[:, 1])
            print(f"depth {depth} iters {iters}: validation AP {ap:.4f}")
            if ap > best_ap:
                best, best_ap = (depth, iters), ap
    m_val = HistGradientBoostingClassifier(max_depth=best[0], max_iter=best[1], learning_rate=0.05, min_samples_leaf=200,
                                           l2_regularization=1.0, random_state=0).fit(a[FEATS], a["y"])
    model = HistGradientBoostingClassifier(max_depth=best[0], max_iter=best[1], learning_rate=0.05, min_samples_leaf=200,
                                           l2_regularization=1.0, random_state=0).fit(tr[FEATS], tr["y"])
    te = te.assign(p=model.predict_proba(te[FEATS])[:, 1])
    v = v.assign(p=m_val.predict_proba(v[FEATS])[:, 1])
    auc, ap, base = roc_auc_score(te["y"], te["p"]), average_precision_score(te["y"], te["p"]), te["y"].mean()
    rng = np.random.default_rng(0)
    byday = {d: g for d, g in te.groupby("date")}
    boots = []
    for _ in range(200):
        pick = rng.choice(list(byday), len(byday))
        s = pd.concat([byday[d] for d in pick])
        if s["y"].nunique() > 1:
            boots.append(roc_auc_score(s["y"], s["p"]))
    lo_, hi_ = np.percentile(boots, [2.5, 97.5])

    L = ["# Boosted decision tree: what precedes a gain?", "",
         f"{len(bars)} stocks, {len(days)} days ({days[0]} to {days[-1]}). Examples: {len(E):,} decision points. Label: buy the bar's "
         f"close, +30% before -15% by the end of the same day. Train: first {n_tr_days} days; test: last {n_te_days} days "
         f"(used once). Model: depth {best[0]}, {best[1]} trees (chosen on the last quarter of the training days).", "",
         f"**Test:** base rate {base * 100:.2f}%, AUC {auc:.3f} (95% CI over days {lo_:.3f}-{hi_:.3f}), average precision "
         f"{ap:.4f} (random = {base:.4f}).", "",
         "| top share of test points by score | points | +30% before -15% | avg trade |", "|---|---|---|---|"]
    te_s = te.sort_values("p", ascending=False)
    for q in (0.001, 0.005, 0.01, 0.05, 0.25):
        top = te_s.head(max(int(len(te_s) * q), 1))
        L.append(f"| top {q * 100:g}% | {len(top):,} | {top['y'].mean() * 100:.1f}% | {top['ret'].mean() * 100:+.1f}% |")
    L.append(f"| all | {len(te):,} | {base * 100:.1f}% | {te['ret'].mean() * 100:+.1f}% |")

    sub = te.sample(min(60_000, len(te)), random_state=0)
    imp = permutation_importance(model, sub[FEATS], sub["y"], scoring="roc_auc", n_repeats=3, random_state=0)
    I = pd.DataFrame({"feature": FEATS, "auc_drop": imp.importances_mean}).sort_values("auc_drop", ascending=False)
    allx = pd.concat([tr, te])
    pos, neg = allx[allx["y"] == 1], allx[allx["y"] == 0]
    I["median_winners"] = [pos[f].median() for f in I["feature"]]
    I["median_others"] = [neg[f].median() for f in I["feature"]]
    L += ["", "## Feature importance on the test days (drop in AUC when the feature is shuffled)", "",
          I.round({"auc_drop": 4, "median_winners": 3, "median_others": 3}).to_string(index=False), ""]

    L += ["## Trading the model blind (first alert per stock and day; thresholds from the validation block, applied to the test days)", ""]
    for n_per_day in (3, 10):
        # choose the probability threshold that gives about n_per_day first-alerts per day on the validation block
        lo_p, hi_p = 0.0, 1.0
        for _ in range(30):
            mid = (lo_p + hi_p) / 2
            k = len(first_per_day(v, v["p"] >= mid)) / len(set(v["date"]))
            lo_p, hi_p = (mid, hi_p) if k > n_per_day else (lo_p, mid)
        L.append(f"- target {n_per_day}/day (threshold {hi_p:.3f}): {summary(first_per_day(te, te['p'] >= hi_p), n_te_days)}")
    mom = (te["pct"] >= 5) & (te["pct"] < 15) & (te["ret10"] >= 10) & (te["burst"] >= 5) & (te["dvol30"] >= 100_000)
    t2 = (te["pct"] >= 0) & (te["pct"] < 25) & (te["ret10"] >= 5) & (te["burst"] >= 3) & (te["dvol30"] >= 25_000)
    L += [f"- rule 'momentum' on the same days: {summary(first_per_day(te, mom), n_te_days)}",
          f"- rule 'tier2' on the same days: {summary(first_per_day(te, t2), n_te_days)}",
          f"- every decision point (reference): avg trade {te['ret'].mean() * 100:+.1f}%", ""]
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "bdt.md"), "w").write("\n".join(L))
    I.to_csv(os.path.join(OUT, "bdt_importance.csv"), index=False)
    print("\n".join(L))


if __name__ == "__main__":
    main()
