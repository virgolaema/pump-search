# Boosted decision tree: what precedes a gain?

588 stocks, 57 days (2026-08-05 to 2026-10-23). Examples: 786,853 decision points. Label: buy the bar's close, +30% before -15% by the end of the same day. Train: first 38 days; test: last 19 days (used once). Model: depth 3, 100 trees (chosen on the last quarter of the training days).

**Test:** base rate 0.62%, AUC 0.897 (95% CI over days 0.851-0.935), average precision 0.0663 (random = 0.0062).

| top share of test points by score | points | +30% before -15% | avg trade |
|---|---|---|---|
| top 0.1% | 244 | 15.6% | -3.9% |
| top 0.5% | 1,222 | 10.6% | -2.2% |
| top 1% | 2,444 | 8.6% | -2.4% |
| top 5% | 12,222 | 6.1% | -2.2% |
| top 25% | 61,114 | 2.2% | -2.3% |
| all | 244,456 | 0.6% | -2.1% |

## Feature importance on the test days (drop in AUC when the feature is shuffled)

      feature  auc_drop  median_winners  median_others
      logmcap    0.1067           6.994          8.152
      range30    0.0168           4.882          1.472
   prev_range    0.0047           0.163          0.076
 run_high_pct    0.0040           9.890          3.261
logavg20_dvol    0.0027           6.287          6.228
          pct    0.0013           2.842          0.000
  dist_high20    0.0010          -0.454         -0.186
        burst    0.0009           1.748          0.966
     logprice    0.0009           0.033          0.307
     active1h    0.0007          11.000         11.000
days_since_50    0.0007          34.000         60.000
          dow    0.0006           2.000          2.000
   dist_low20    0.0006           0.200          0.101
    logdvol30    0.0002           4.905          4.866
        ret10    0.0001           0.046          0.000
     prev_ret    0.0000          -0.019         -0.006
rel_vol_today    0.0000           0.371          0.363
        ret30    0.0000           0.334          0.000
    from_high    0.0000          -5.561         -3.000
 n_spike30_20   -0.0001           1.000          0.000
          tod   -0.0001         695.000        755.000
   max_gain_5   -0.0045           0.180          0.081

## Trading the model blind (first alert per stock and day; thresholds from the validation block, applied to the test days)

- target 3/day (threshold 0.226): 145 alerts (7.6/day), +30% before -15%: 10%, avg trade -4.0%, P&L at $100 each $-575
- target 10/day (threshold 0.130): 398 alerts (20.9/day), +30% before -15%: 11%, avg trade -2.6%, P&L at $100 each $-1,034
- rule 'momentum' on the same days: 30 alerts (1.6/day), +30% before -15%: 13%, avg trade -4.0%, P&L at $100 each $-120
- rule 'tier2' on the same days: 404 alerts (21.3/day), +30% before -15%: 10%, avg trade -2.6%, P&L at $100 each $-1,065
- every decision point (reference): avg trade -2.1%
