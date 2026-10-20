"""Do SEC filings (offerings, financing 8-Ks, charter changes, late filings) predict which spikes fade?

Uses the recorded what-if trades (backtest/tier2_trades.csv: 'tier2' = looser-tier flags bought at +20%,
'control' = every liquid stock bought at +20%; exit +50%/-50% or next-day close). For each trade, the filings
accepted by the SEC BEFORE the entry time are turned into features, fixed in advance (no tuning):
  offering   any 424B prospectus in the prior 30 days
  shelf      any S-1/S-3/F-1/F-3 registration (or amendment) in the prior 30 days
  financing  8-K with item 3.02 (unregistered equity sale) or 1.01 (material agreement) in the prior 30 days
  charter    8-K with item 5.03 or 3.03 (charter change, e.g. reverse split) in the prior 90 days
  late       NT 10-K / NT 10-Q in the prior 90 days
  fresh8k    8-K or 6-K accepted in the 24 hours before entry
  dilution   offering or shelf or financing or charter
Rule-based on form types and 8-K item codes, not on the text of the filings."""
import os
import sys
import time

import numpy as np
import pandas as pd
import requests

from .backtest import OUT

UA = {"User-Agent": "pump-search research bot github.com/virgolaema/pump-search", "Accept-Encoding": "gzip, deflate"}
FEATS = ["offering", "shelf", "financing", "charter", "late", "fresh8k", "dilution"]


def sec_get(url, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"SEC {r.status_code} for {url}: {r.text[:200]!r}")
            if r.status_code in (429, 503):
                time.sleep(5 * (k + 1))
                continue
            return None
        except Exception as e:
            print(f"SEC request error for {url}: {type(e).__name__}: {e}")
            time.sleep(2)
    return None


def fetch_filings(tickers):
    cmap = sec_get("https://www.sec.gov/files/company_tickers.json") or {}
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in cmap.values()}
    out, miss = {}, []
    for t in tickers:
        c = cik.get(t)
        if c is None:
            miss.append(t)
            continue
        j = sec_get(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
        time.sleep(0.12)
        if not j:
            miss.append(t)
            continue
        r = j["filings"]["recent"]
        d = pd.DataFrame({k: r.get(k) for k in ("form", "filingDate", "acceptanceDateTime", "items")})
        d["acc"] = pd.to_datetime(d["acceptanceDateTime"], utc=True, errors="coerce")
        d["items"] = d["items"].fillna("")
        out[t] = d.dropna(subset=["acc"])
    print(f"filings found for {len(out)}/{len(tickers)} tickers; no CIK or no data: {len(miss)}")
    return out, miss


def features(d, T):
    """d: filings of one ticker; T: entry time (UTC)."""
    p = d[d["acc"] < T]
    age = (T - p["acc"]).dt.total_seconds() / 86400
    form, items = p["form"].fillna(""), p["items"]
    has = lambda mask, days: bool((mask & (age <= days)).any())
    is8k = form.isin(["8-K", "8-K/A"])
    f = {
        "offering": has(form.str.startswith("424B"), 30),
        "shelf": has(form.str.startswith(("S-1", "S-3", "F-1", "F-3")), 30),
        "financing": has(is8k & items.str.contains(r"\b(?:3\.02|1\.01)\b"), 30),
        "charter": has(is8k & items.str.contains(r"\b(?:5\.03|3\.03)\b"), 90),
        "late": has(form.str.startswith("NT "), 90),
        "fresh8k": has(form.isin(["8-K", "6-K"]), 1),
    }
    f["dilution"] = f["offering"] or f["shelf"] or f["financing"] or f["charter"]
    return f


def welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return np.nan
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return (a.mean() - b.mean()) / se if se > 0 else np.nan


def analyse(T, filings):
    rows = []
    for r in T.itertuples():
        d = filings.get(r.ticker)
        if d is None:
            continue
        rows.append({**r._asdict(), **features(d, pd.Timestamp(r.entry_time).tz_convert("UTC"))})
    return pd.DataFrame(rows)


def main():
    T = pd.read_csv(os.path.join(OUT, "tier2_trades.csv"))
    T = T[T["group"].isin(["tier2", "control"])].copy()
    T["entry_time"] = pd.to_datetime(T["entry_time"], utc=True)
    filings, miss = fetch_filings(sorted(T["ticker"].unique()))
    F = analyse(T, filings)
    F.to_csv(os.path.join(OUT, "filings_features.csv"), index=False)
    cover = F["ticker"].nunique() / T["ticker"].nunique() * 100
    L = ["# Do SEC filings predict which spikes fade?", "",
         f"Trades with filings data: {len(F)} of {len(T)} (tickers covered: {cover:.0f}%). Exit: +50% / -50% / next-day close; "
         f"ret = return on the trade after 1% slippage each way. Features use only filings accepted before entry. "
         f"Seven features fixed in advance; |t| above about 2.7 would be needed to take one seriously.", ""]
    dates = sorted(F["date"].unique())
    mid = dates[len(dates) // 2]
    for g in ["control", "tier2"]:
        D = F[F["group"] == g]
        L += [f"## Group: {g} ({len(D)} trades, avg return {D['ret'].mean() * 100:+.1f}%)", "",
              "| feature | trades with | avg with | avg without | difference | t | with feature: +50% hits | first half diff | second half diff |",
              "|---|---|---|---|---|---|---|---|---|"]
        for f in FEATS:
            a, b = D[D[f]]["ret"], D[~D[f]]["ret"]
            h = lambda D2: (D2[D2[f]]["ret"].mean() - D2[~D2[f]]["ret"].mean()) * 100 if D2[f].any() and (~D2[f]).any() else np.nan
            L.append(f"| {f} | {len(a)} | {a.mean() * 100:+.1f}% | {b.mean() * 100:+.1f}% | {(a.mean() - b.mean()) * 100:+.1f} pts | "
                     f"{welch(a, b):+.1f} | {(D[D[f]]['how'] == 'tp').mean() * 100:.0f}% | {h(D[D['date'] <= mid]):+.1f} | {h(D[D['date'] > mid]):+.1f} |")
        keep, drop = D[~D["dilution"]], D[D["dilution"]]
        L += ["", f"P&L at $100 per trade: all {len(D)} trades ${100 * D['ret'].sum():+,.0f}; "
                  f"without dilution-flagged trades ({len(keep)}) ${100 * keep['ret'].sum():+,.0f} "
                  f"(avg {keep['ret'].mean() * 100:+.1f}%); only dilution-flagged ({len(drop)}) ${100 * drop['ret'].sum():+,.0f} "
                  f"(avg {drop['ret'].mean() * 100:+.1f}%).", ""]
    open(os.path.join(OUT, "filings_test.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
