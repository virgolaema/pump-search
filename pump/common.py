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
os.makedirs(DATA, exist_ok=True)

# Universe
PRICE_MIN, PRICE_MAX = 0.10, 5.00
MIN_DAY_VOLUME = 50_000
EXCHANGES = ["NMS", "NGM", "NCM", "NYQ", "ASE"]
UNIVERSE_MAX = 600

# Prediction rule (frozen before outcomes are known; change only with a dated note in README)
MAX_PCT_AT_FLAG = 15.0      # stock must not have spiked yet (% vs previous close)
BURST_MIN = 5.0             # last-30-min volume / median 30-min volume of prior days
RVOL_MIN = 2.0              # today's volume / expected volume at this time of day
ST_RATE_MIN = 10.0          # StockTwits messages per hour
ST_RATE_MULT = 3.0          # vs. the ticker's own median rate in earlier snapshots
REFLAG_HOURS = 24           # do not re-flag the same ticker within this window

# Outcomes
HIT_GAIN = 30.0             # prediction is a hit if high reaches +30% over flag price...
HIT_DAYS = 3                # ...within this many trading days
SPIKE_GAIN = 50.0           # a spike event: day high >= +50% vs previous close
SPIKE_START = 20.0          # spike start time = first 5-min bar with high >= +20%
LEAD_DAYS = 3               # a flag counts for an event if made up to 3 days before its start


def now_utc():
    return datetime.now(timezone.utc)


def read_csv(path, **kw):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kw)


def append_csv(path, df):
    if df is None or df.empty:
        return
    header = not os.path.exists(path) or os.path.getsize(path) == 0
    df.to_csv(path, mode="a", header=header, index=False)


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
