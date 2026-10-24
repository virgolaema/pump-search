"""Score the 10-minute flags (data/predictions.csv, rule v3 from 2026-10-19) with the same trade model as the
minute watcher: buy at the flag price +1%, sell at +30% / -15% (stop wins ties) or at the same-day close, -1% on
exit, on 1-minute bars. Results go to data/flag_trades.csv, by category:
  momentum     the backtested momentum rule
  social+vol   StockTwits signal together with a 5x volume burst (alerted)
  social only  StockTwits signal without the volume burst (logged, not alerted)
Yahoo keeps 1-minute bars for about 7 days, so flags are scored daily (and back-filled up to 6 days)."""
import pandas as pd

from . import market
from .common import FLAG_TRADES, PREDICTIONS, append_csv, read_csv
from .replay_1m import fill_grid
from .watch import score

V3_START = "2026-10-19"
CATS = ["momentum", "social+vol", "social only"]


def category(reasons):
    r = str(reasons)
    if "momentum" in r:
        return "momentum"
    if "st_" in r and "vol x" in r:
        return "social+vol"
    if "st_" in r:
        return "social only"
    return None


def score_pending(now):
    now_ny = pd.Timestamp(now).tz_convert(market.NY)
    p = read_csv(PREDICTIONS)
    if p.empty:
        return 0
    p = p[p["ts"] >= V3_START].copy()
    p["cat"] = p["reasons"].map(category)
    p["day"] = pd.to_datetime(p["ts"], utc=True).dt.tz_convert(market.NY).dt.date
    complete = (p["day"] < now_ny.date()) | ((p["day"] == now_ny.date()) & (now_ny.hour >= 20))
    recent = p["day"] >= (now_ny - pd.Timedelta(days=6)).date()
    p = p[p["cat"].notna() & complete & recent]
    done = read_csv(FLAG_TRADES)
    if not done.empty:
        keys = set(zip(done["ts"], done["ticker"]))
        p = p[[(a, b) not in keys for a, b in zip(p["ts"], p["ticker"])]]
    if p.empty:
        return 0
    raw = market.download(sorted(set(p["ticker"])), period="7d", interval="1m", prepost=True)
    rows = []
    for f in p.to_dict("records"):
        if f["ticker"] not in raw:
            continue
        x = fill_grid(raw[f["ticker"]])
        if (x.index.date == f["day"]).any():
            rows.append({"ts": f["ts"], "ticker": f["ticker"], "cat": f["cat"], "price": f["price"],
                         **score(f, x)})
    append_csv(FLAG_TRADES, pd.DataFrame(rows))
    print(f"scored {len(rows)} 10-min flags")
    return len(rows)


def report_lines(day):
    t = read_csv(FLAG_TRADES)
    if t.empty:
        return ["**10-min flags, trade model:** none scored yet.", ""]
    t["day"] = pd.to_datetime(t["ts"], utc=True).dt.tz_convert(market.NY).dt.date
    fmt = lambda x: (f"{len(x)} trades, {(x['how'] == 'tp').mean() * 100:.0f}% +30%, {(x['how'] == 'stop').mean() * 100:.0f}% -15%, "
                     f"avg {x['ret'].mean() * 100:+.1f}% (± {x['ret'].std() / max(len(x), 1) ** 0.5 * 100:.1f}), "
                     f"P&L ${100 * x['ret'].sum():+,.0f}") if len(x) else "none"
    out = [f"**10-min flags, trade model** (since {V3_START}; buy at flag +1%, +30% / -15% / same-day close, -1% exit; $100 each):"]
    for c in CATS:
        out.append(f"- {c}: today {fmt(t[(t['cat'] == c) & (t['day'] == day)])}; all {fmt(t[t['cat'] == c])}")
    st = t[t["cat"].isin(["social+vol", "social only"])]
    out.append(f"- any StockTwits signal, all days: {fmt(st)}")
    return out + [""]
