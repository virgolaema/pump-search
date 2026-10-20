# Backtest (blind split)

Tickers: 595 (watchlist of 2026-10-20). Days: 58 (2026-07-30 to 2026-10-20); train < 2026-09-23 (38 d), test >= 2026-09-23 (20 d).
Trade model: entry = flag close +1%, exit +30% / -15% / end of next trading day. Break-even win rate ~33%.

**Chosen on train:** {'pct_lo': 5.0, 'pct_hi': 15.0, 'burst': 50.0, 'ret10': 3.0, 'dvol': 300000.0}
- train: {'flags': 61, 'per_day': 1.6, 'win': 31.1, 'stop': 32.8, 'mean_ret': 4.27, 'med_max_up': 13.8, 'events': 340, 'caught_early': 0, 'caught_with_30pct_left': 28}
- **test: {'flags': 56, 'per_day': 2.8, 'win': 28.6, 'stop': 46.4, 'mean_ret': 1.22, 'med_max_up': 13.1, 'events': 213, 'caught_early': 3, 'caught_with_30pct_left': 20}**

Baseline random entries (−5%..+15%, ≥$25k/30min): train {'n': 5909, 'win': 3.0, 'mean_ret': -1.18}, test {'n': 2927, 'win': 4.3, 'mean_ret': -1.98}

Top 10 rules on train (mean return per trade):

 pct_lo  pct_hi  burst  ret10   dvol  flags  per_day  win  stop  mean_ret  med_max_up  events  caught_early  caught_with_30pct_left
      5      15     50      3 300000     61      1.6 31.1  32.8      4.27        13.8     340             0                      28
      5      15     50      3 100000     73      1.9 27.4  30.1      2.71        11.8     340             0                      29
      0      15     50      3 300000     86      2.3 26.7  33.7      2.70        13.1     340             0                      32
      5      25     20     10 300000     43      1.1 27.9  41.9      2.42        11.0     340             2                      15
      5      15     50      3  25000     86      2.3 25.6  25.6      2.06        10.7     340             0                      30
     -5      15     50      3 300000    122      3.2 23.0  32.0      1.80        11.2     340             0                      38
      5      25     50      3 300000    122      3.2 26.2  42.6      1.72        13.8     340             0                      53
      0      25     20     10 300000     47      1.2 25.5  44.7      1.48        11.0     340             2                      15
      5      25     50      5 300000     76      2.0 22.4  40.8      1.41        13.8     340             0                      35
     -5      25     20     10 300000     50      1.3 26.0  46.0      1.39        10.6     340             2                      15
