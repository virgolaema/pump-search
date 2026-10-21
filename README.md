# pump-search

Paper test: can StockTwits chatter plus unusual volume flag low-price US stocks ($0.10–$5, market cap < $300M, ≥50k shares/day, Nasdaq/NYSE/AMEX) before they spike? Observation only, no trading.

- Scheduling: GitHub's cron never fired for this repo, so `loop.yml` runs `scripts/loop.sh` (collect every 10 min on weekdays 08:00–24:00 UTC, evaluate at 00:20 UTC), ~5.7 h per job, then re-dispatches itself. Stop it by committing a file named `STOP` or disabling the workflow; it ends on its own after 2026-11-13. `collect.yml`/`evaluate.yml` are manual-run only.
- `pump/collect.py` rebuilds the watchlist once a day from the Yahoo screener (up to 600 names), snapshots 5-min price/volume and StockTwits message rates, and appends flags to `data/predictions.csv`.
- `pump/evaluate.py` It scores flags and finds the day's spikes, then writes `reports/YYYY-MM-DD.md`.

Minute watcher (from 2026-10-21, `pump/watch.py`): after each 10-minute scan, `collect.py` writes a short list of up to 130 actively traded names (`data/hotlist.csv`); until the next scan, `watch.py` fetches their 1-minute bars every minute, rebuilds the same features, and logs the first hit per ticker and rule to `data/watch_flags.csv` (rules: `momentum` = the push-alert rule, `tier2` = looser). Momentum hits also send the ntfy/issue alert, once per ticker per day. After the close, `evaluate.py` scores them (buy at the flagged minute +1%, sell +30% / −15% / same-day close, −1% on exit) into `data/watch_outcomes.csv` and adds a section to the daily report. Motivation: `backtest/replay_1m.md` (5 days: checking every minute caught 4 of 46 spikes, average trade +0.7% on 26 trades; the 10-minute system caught 0). Rules and thresholds are frozen from here on so that the live results are out-of-sample.

Alerts (v3, from 2026-10-19): an ntfy.sh push (topic in `loop.yml`) plus a GitHub issue labelled `alert` when either
- **momentum** (chosen by the blind backtest, `backtest/results.md`): price +5% to +15% vs previous close, +10% or more in the last 10 min, 30-min volume ≥5× the same time of day on the prior 4 days, and ≥$100k traded in 30 min; or
- **social + volume** (not backtestable): a StockTwits signal (rate ≥10/h and ≥3× its baseline, or newly trending) with volume ≥5× and price between −5% and +15%.

StockTwits-only signals are logged as flags but not alerted. Earlier rules: v1 until 2026-10-16 14:20 UTC (over-flagged at the open), v2 until 2026-10-18 (any 5× volume burst).

Backtest (`pump/backtest.py`, run by `backtest.yml`): 579 watchlist stocks, 58 days of 5-min bars, a check every 10 min using only past data; rules are picked on the first 38 days and scored once on the last 20. Trade model: buy at flag +1%, sell at +30%, stop at −15%, or close at the end of the next trading day. Result for the chosen rule on the test days: 37 alerts (≈2/day), 24% hit +30% (random entries: 4%), 51% stopped out, mean trade −0.5%; only 2 of 217 spikes were flagged before reaching +20%.

Scoring:
- A flag is a hit if the price reaches +30% over the flag price within 2 trading days (flag day + next).
- A spike event is a day with an intraday high ≥ +50% vs the previous close; it starts at the first 5-min bar at +20%. It counts as caught if it was flagged up to 2 days before the start.
- The baseline is the share of watched stocks that hit +30% intraday on the day.
