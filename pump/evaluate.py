"""Daily evaluation: score past flags, detect today's spikes, write reports/YYYY-MM-DD.md.

Run once after the US close."""
import os

import numpy as np
import pandas as pd

from . import market
from .common import (EVENTS, HIT_DAYS, HIT_GAIN, LEAD_DAYS, OUTCOMES, PREDICTIONS, PRICE_MAX, REPORTS, RUNLOG,
                     SPIKE_GAIN, SPIKE_START, UNIVERSE, now_utc, read_csv)


def trading_days_between(bars, start_ts):
    days = sorted({d for d in bars.index.date if d >= start_ts.date()})
    return days


def score_predictions(preds, bars):
    """Max gain over the flag price within HIT_DAYS trading days after the flag."""
    out = []
    for _, p in preds.iterrows():
        b = bars.get(p["ticker"])
        ts = pd.Timestamp(p["ts"]).tz_convert(market.NY)
        if b is None:
            out.append({"ts": p["ts"], "ticker": p["ticker"], "max_gain": np.nan, "days": 0, "final": False})
            continue
        days = trading_days_between(b, ts)[:HIT_DAYS]
        after = b[(b.index > ts) & np.isin(b.index.date, days)]
        mg = (after["High"].max() / p["price"] - 1) * 100 if len(after) else np.nan
        out.append({"ts": p["ts"], "ticker": p["ticker"], "max_gain": round(mg, 1) if not np.isnan(mg) else np.nan,
                    "days": len(days), "final": len(days) >= HIT_DAYS})
    o = pd.DataFrame(out)
    if not o.empty:
        o["hit"] = o["max_gain"] >= HIT_GAIN
    return o


def find_events(bars, today):
    ev, n_up30, n = [], 0, 0
    for t, b in bars.items():
        pc, tb = market.prev_close_and_today(b, today)
        if pc is None or tb.empty or pc > PRICE_MAX:
            continue
        n += 1
        gain = (tb["High"].max() / pc - 1) * 100
        if gain >= HIT_GAIN:
            n_up30 += 1
        if gain >= SPIKE_GAIN:
            start = tb.index[tb["High"] >= pc * (1 + SPIKE_START / 100)][0]
            ev.append({"date": str(today), "ticker": t, "prev_close": pc, "max_gain": round(gain, 1),
                       "start": start.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")})
    return pd.DataFrame(ev), n_up30, n


def main():
    now = now_utc()
    today = pd.Timestamp(now).tz_convert(market.NY).date()
    preds = read_csv(PREDICTIONS)
    uni = read_csv(UNIVERSE)
    universe = set(uni["ticker"]) if not uni.empty else set()

    old = read_csv(OUTCOMES)
    done = old[old["final"]] if not old.empty else pd.DataFrame(columns=["ts", "ticker"])
    done_keys = set(zip(done["ts"], done["ticker"]))
    open_preds = preds[[(a, b) not in done_keys for a, b in zip(preds["ts"], preds["ticker"])]] if not preds.empty else preds

    gainers = [s for s in market.predefined("day_gainers", 250) + market.predefined("small_cap_gainers", 250)]
    want = universe | set(gainers) | (set(open_preds["ticker"]) if not open_preds.empty else set())
    bars = market.download(sorted(want), period="5d", interval="5m", prepost=True)

    # outcomes
    new = score_predictions(open_preds, bars) if not open_preds.empty else pd.DataFrame()
    outcomes = pd.concat([done, new], ignore_index=True)
    outcomes.to_csv(OUTCOMES, index=False)

    # spike events today
    ev, n_up30, n_watch = find_events(bars, today)
    if not ev.empty:
        ev["in_universe"] = ev["ticker"].isin(universe)
        caught, lead = [], []
        for _, e in ev.iterrows():
            st = pd.Timestamp(e["start"])
            p = preds[(preds["ticker"] == e["ticker"]) & (pd.to_datetime(preds["ts"]) < st) &
                      (pd.to_datetime(preds["ts"]) >= st - pd.Timedelta(days=LEAD_DAYS))] if not preds.empty else []
            caught.append(len(p) > 0)
            lead.append(round((st - pd.to_datetime(p["ts"]).min()).total_seconds() / 60) if len(p) else np.nan)
        ev["flagged_before"] = caught
        ev["lead_min"] = lead
        allev = read_csv(EVENTS)
        if not allev.empty:
            allev = allev[allev["date"] != str(today)]
        pd.concat([allev, ev], ignore_index=True).to_csv(EVENTS, index=False)
    base_rate = n_up30 / n_watch * 100 if n_watch else np.nan

    write_report(today, now, preds, outcomes, ev, base_rate, n_watch)


def fmt_et(ts):
    return pd.Timestamp(ts).tz_convert(market.NY).strftime("%H:%M ET")


def write_report(today, now, preds, outcomes, ev, base_rate, n_watch):
    os.makedirs(REPORTS, exist_ok=True)
    L = [f"# Pump watch — {today}", ""]
    tp = preds[pd.to_datetime(preds["ts"]).dt.tz_convert(market.NY).dt.date == today] if not preds.empty else preds
    om = {(r.ts, r.ticker): r for r in outcomes.itertuples()} if not outcomes.empty else {}
    L.append(f"**Flags today: {len(tp)}**")
    for r in tp.itertuples():
        o = om.get((r.ts, r.ticker))
        g = f"{o.max_gain:+.0f}% since" if o is not None and not pd.isna(o.max_gain) else "n/a"
        L.append(f"- {r.ticker} {fmt_et(r.ts)} @ ${r.price:.2f} ({r.pct:+.0f}% at flag) — {r.reasons} — max {g}")
    L.append("")
    if ev is None or ev.empty:
        L.append(f"**Spikes today (≥+{SPIKE_GAIN:.0f}%): 0**")
    else:
        k = int(ev["flagged_before"].sum())
        L.append(f"**Spikes today (≥+{SPIKE_GAIN:.0f}%): {len(ev)}, flagged in advance: {k}**")
        for r in ev.sort_values("max_gain", ascending=False).itertuples():
            tag = (f"flagged {r.lead_min:.0f} min before start" if r.flagged_before
                   else ("missed (watched)" if r.in_universe else "missed (not in watchlist)"))
            L.append(f"- {r.ticker} {r.max_gain:+.0f}%, started {fmt_et(r.start)} — {tag}")
    L.append("")
    fin = outcomes[outcomes["final"]] if not outcomes.empty else outcomes
    allev = read_csv(EVENTS)
    hits = int(fin["hit"].sum()) if not fin.empty else 0
    prec = f"{hits / len(fin) * 100:.0f}%" if len(fin) else "n/a"
    rec = (f"{int(allev['flagged_before'].sum())}/{len(allev)}" if not allev.empty else "0/0")
    L.append(f"**Running totals:** {len(preds)} flags, {len(fin)} resolved, {hits} hit +{HIT_GAIN:.0f}% within "
             f"{HIT_DAYS} days (precision {prec}). Spikes caught in advance: {rec}.")
    br = f"{base_rate:.1f}%" if not pd.isna(base_rate) else "n/a"
    L.append(f"**Baseline:** {br} of {n_watch} low-price stocks hit +{HIT_GAIN:.0f}% intraday today "
             f"(what random picking would roughly give per day).")
    log = read_csv(RUNLOG)
    if not log.empty:
        lt = log[pd.to_datetime(log["ts"]).dt.tz_convert(market.NY).dt.date == today]
        st = lt["st_status"].value_counts().to_dict() if not lt.empty else {}
        L.append(f"**Data health:** {len(lt)} collection runs today; StockTwits status {st or 'n/a'}.")
    L.append("")
    path = os.path.join(REPORTS, f"{today}.md")
    with open(path, "w") as f:
        f.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
