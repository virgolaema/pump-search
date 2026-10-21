"""Shared paths, parameters and CSV helpers. All timestamps are UTC ISO strings."""
import os
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPORTS = os.path.join(ROOT, "reports")

UNIVERSE = os.path.join(DATA, "universe.csv")
SNAPSHOTS = os.path.join(DATA, "snapshots.csv")
ST_TRENDING = os.path.join(DATA, "st_trending.csv")
PREDICTIONS = os.path.join(DATA, "predictions.csv")
OUTCOMES = os.path.join(DATA, "outcomes.csv")
EVENTS = os.path.join(DATA, "events.csv")
RUNLOG = os.path.join(DATA, "runlog.csv")
ALERTS = os.path.join(DATA, "alerts.csv")
HOTLIST = os.path.join(DATA, "hotlist.csv")
WATCH = os.path.join(DATA, "watch_flags.csv")
WATCH_OUT = os.path.join(DATA, "watch_outcomes.csv")
os.makedirs(DATA, exist_ok=True)

# Universe
PRICE_MIN, PRICE_MAX = 0.10, 5.00
MIN_DAY_VOLUME = 50_000
MCAP_MAX = 300e6           # pumps target micro/small caps; drops big names that just trade cheaply
EXCHANGES = ["NMS", "NGM", "NCM", "NYQ", "ASE"]
UNIVERSE_MAX = 600

# Prediction rules. v3 (2026-10-18): alerts use the momentum rule chosen by the blind backtest
# (backtest/results.md, train 38 d / test 20 d). StockTwits flags are logged and alerted only
# together with a volume burst; they are not backtestable (no history).
MOM_PCT_LO, MOM_PCT_HI = 5.0, 15.0   # % vs previous close
MOM_RET10 = 10.0                     # % price change over the last 10 min
MOM_BURST = 5.0                      # 30-min volume vs same time of day on prior 4 days
MOM_DVOL = 100_000                   # $ traded in the last 30 min
MAX_PCT_AT_FLAG = 15.0      # stock must not have spiked yet (% vs previous close)
MIN_PCT_AT_FLAG = -5.0      # ...and must not be selling off (v2, 2026-10-16 14:20 UTC)
BURST_MIN = 5.0             # last-30-min volume / same-time-of-day 30-min volume of prior days (v2)
RVOL_MIN = 2.0              # today's volume / expected volume at this time of day
ST_RATE_MIN = 10.0          # StockTwits messages per hour
ST_RATE_MULT = 3.0          # vs. the ticker's own median rate in earlier snapshots
REFLAG_HOURS = 24           # do not re-flag the same ticker within this window

# Outcomes
HIT_GAIN = 30.0             # prediction is a hit if high reaches +30% over flag price...
HIT_DAYS = 2                # ...within this many trading days (flag day + next)
SPIKE_GAIN = 50.0           # a spike event: day high >= +50% vs previous close
SPIKE_START = 20.0          # spike start time = first 5-min bar with high >= +20%
LEAD_DAYS = 2               # a flag counts for an event if made up to 2 days before its start


def now_utc():
    return datetime.now(timezone.utc)


def read_csv(path, **kw):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    kw.setdefault("keep_default_na", False)   # ticker "NA" (Nano Labs) must stay a string
    kw.setdefault("na_values", [""])
    return pd.read_csv(path, **kw)


def append_csv(path, df):
    if df is None or df.empty:
        return
    header = not os.path.exists(path) or os.path.getsize(path) == 0
    df.to_csv(path, mode="a", header=header, index=False)


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
