# pump-search

Paper test: can StockTwits chatter plus unusual volume flag low-price US stocks ($0.10–$5, market cap < $300M, ≥50k shares/day, Nasdaq/NYSE/AMEX) before they spike? Observation only, no trading.

- `pump/collect.py` runs every 10 min on weekdays, 04:00–20:00 ET (GitHub Actions, `collect.yml`). It rebuilds the watchlist once a day from the Yahoo screener (up to 600 names), snapshots 5-min price/volume and StockTwits message rates, and appends flags to `data/predictions.csv`.
- `pump/evaluate.py` runs after post-market (`evaluate.yml`). It scores flags and finds the day's spikes, then writes `reports/YYYY-MM-DD.md`.

Flag rule (frozen, see `pump/common.py`). A stock is flagged if it is still below +15% vs the previous close and at least one of these holds:
- the last 30-min volume is ≥5× its usual 30-min volume, with ≥$50k traded and (in regular hours) relative volume ≥2;
- the StockTwits message rate is ≥10/h and ≥3× its own baseline, or ≥20/h if there is no baseline yet;
- the stock is newly on StockTwits trending.

Scoring:
- A flag is a hit if the price reaches +30% over the flag price within 2 trading days (flag day + next).
- A spike event is a day with an intraday high ≥ +50% vs the previous close; it starts at the first 5-min bar at +20%. It counts as caught if it was flagged up to 2 days before the start.
- The baseline is the share of watched stocks that hit +30% intraday on the day.
