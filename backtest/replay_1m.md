# 1-minute replay: does faster data help?

584 stocks; days with baseline and a previous close: 5 (2026-10-15 to 2026-10-21). Spikes (day high >= +50% vs previous close) on those days: 46. Buy at the flagged minute's close +1%; sell +30% / -15% / same-day close, -1% on exit. Small sample: a direction, not a verdict.

## Rule: momentum

| set-up | flags | per day | +30% before -15% | -15% first | avg trade | spikes flagged before reaching +20% | of those, with 30%+ still to go |
|---|---|---|---|---|---|---|---|
| A 5m bars, every 10 min (live) | 6 | 1.2 | 17% | 50% | -5.1% | 0 of 46 | 0 |
| B 5m bars, every 5 min | 12 | 2.4 | 8% | 33% | -4.0% | 0 of 46 | 0 |
| C 1m bars, every 10 min | 6 | 1.2 | 17% | 50% | -5.1% | 0 of 46 | 0 |
| D 1m bars, every minute | 26 | 5.2 | 23% | 27% | +0.7% | 4 of 46 | 4 |
| D+2 as D, filled 2 min later | 26 | 5.2 | 15% | 31% | -3.2% | 4 of 46 | 3 |

## Rule: tier2

| set-up | flags | per day | +30% before -15% | -15% first | avg trade | spikes flagged before reaching +20% | of those, with 30%+ still to go |
|---|---|---|---|---|---|---|---|
| A 5m bars, every 10 min (live) | 116 | 23.2 | 14% | 19% | -1.8% | 3 of 46 | 3 |
| B 5m bars, every 5 min | 157 | 31.4 | 11% | 19% | -2.3% | 4 of 46 | 4 |
| C 1m bars, every 10 min | 113 | 22.6 | 14% | 19% | -1.6% | 3 of 46 | 3 |
| D 1m bars, every minute | 215 | 43.0 | 10% | 17% | -2.4% | 10 of 46 | 10 |
| D+2 as D, filled 2 min later | 215 | 43.0 | 10% | 17% | -2.1% | 10 of 46 | 9 |
