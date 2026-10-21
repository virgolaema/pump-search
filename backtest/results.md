# Backtest (blind split)

Tickers: 582 (watchlist of 2026-10-21). Days: 58 (2026-07-31 to 2026-10-21); train < 2026-09-24 (38 d), test >= 2026-09-24 (20 d).
Trade model: entry = flag close +1%, exit +30% / -15% / end of next trading day. Break-even win rate ~33%.

**Chosen on train:** {'pct_lo': 5.0, 'pct_hi': 15.0, 'burst': 50.0, 'ret10': 3.0, 'dvol': 300000.0}
- train: {'flags': 60, 'per_day': 1.6, 'win': 28.3, 'stop': 35.0, 'mean_ret': 2.57, 'med_max_up': 13.5, 'events': 320, 'caught_early': 0, 'caught_with_30pct_left': 25}
- **test: {'flags': 52, 'per_day': 2.6, 'win': 26.9, 'stop': 46.2, 'mean_ret': 0.39, 'med_max_up': 11.8, 'events': 183, 'caught_early': 2, 'caught_with_30pct_left': 21}**

Baseline random entries (−5%..+15%, ≥$25k/30min): train {'n': 5922, 'win': 3.2, 'mean_ret': -1.08}, test {'n': 2723, 'win': 3.9, 'mean_ret': -2.06}

Top 10 rules on train (mean return per trade):

 pct_lo  pct_hi  burst  ret10   dvol  flags  per_day  win  stop  mean_ret  med_max_up  events  caught_early  caught_with_30pct_left
      5      15     50      3 300000     60      1.6 28.3  35.0      2.57        13.5     320             0                      25
      5      15     50   -100 300000    198      5.2 24.2  34.3      2.28        11.0     320             1                      77
      5      15     50      3 100000     75      2.0 26.7  30.7      1.95        10.2     320             1                      27
      0      15     50      3 300000     82      2.2 24.4  34.1      1.60        12.0     320             0                      28
      5      15     20      3 100000    156      4.1 22.4  30.1      1.55         8.9     320             7                      44
      5      25     50      5 300000     65      1.7 24.6  46.2      1.12        13.2     320             0                      27
      0      15     20      3 100000    217      5.7 19.4  28.1      0.91         8.3     320             7                      48
      5      25     20     10 100000     49      1.3 22.4  40.8      0.90        11.3     320             4                      16
     -5      25     20      5 300000    170      4.5 23.5  40.0      0.84         9.5     320             4                      48
      0      25     20      5 300000    151      4.0 23.8  41.7      0.84         9.9     320             4                      44
