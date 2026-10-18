# Backtest (blind split)

Tickers: 579 (watchlist of 2026-10-16). Days: 58 (2026-07-28 to 2026-10-16); train < 2026-09-21 (38 d), test >= 2026-09-21 (20 d).
Trade model: entry = flag close +1%, exit +30% / -15% / end of next trading day. Break-even win rate ~33%.

**Chosen on train:** {'pct_lo': 5.0, 'pct_hi': 15.0, 'burst': 5.0, 'ret10': 10.0, 'dvol': 100000.0}
- train: {'flags': 43, 'per_day': 1.1, 'win': 23.3, 'stop': 25.6, 'mean_ret': 2.88, 'med_max_up': 8.3, 'events': 320, 'caught_early': 6, 'caught_with_30pct_left': 9}
- **test: {'flags': 37, 'per_day': 1.9, 'win': 24.3, 'stop': 51.4, 'mean_ret': -0.53, 'med_max_up': 10.9, 'events': 217, 'caught_early': 2, 'caught_with_30pct_left': 8}**

Baseline random entries (−5%..+15%, ≥$25k/30min): train {'n': 5652, 'win': 3.4, 'mean_ret': -1.04}, test {'n': 2937, 'win': 4.3, 'mean_ret': -2.11}

Top 10 rules on train (mean return per trade):

 pct_lo  pct_hi  burst  ret10   dvol  flags  per_day  win  stop  mean_ret  med_max_up  events  caught_early  caught_with_30pct_left
      5      15      5     10 100000     43      1.1 23.3  25.6      2.88         8.3     320             6                       9
      0      15     10     10  25000     40      1.1 25.0  25.0      2.63         8.2     320             7                      12
      5      15      5     10  25000     53      1.4 20.8  28.3      1.23         7.7     320             7                      11
      0      15      5     10 100000     51      1.3 21.6  33.3      1.22         7.9     320             6                      10
      5      15      3     10 100000     53      1.4 20.8  32.1      1.15         8.1     320             7                      10
      5      15      3     10  25000     69      1.8 20.3  31.9      0.77         7.7     320            10                      14
      5      40     10     10 300000     99      2.6 25.3  48.5      0.74        12.4     320             4                      29
      0      40     10     10 300000    103      2.7 25.2  48.5      0.70        12.4     320             4                      29
     -5      15     10     10  25000     45      1.2 22.2  33.3      0.67         7.9     320             7                      12
      5      40     10     10 100000    115      3.0 25.2  47.0      0.64        11.0     320             7                      34
