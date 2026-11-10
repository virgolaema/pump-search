# Event study: price after a live flag

521 live flags on 16 trading days (2026-10-19 to 2026-11-09). Mean return ± standard error in %, measured from the last 5-minute close before the flag, no slippage or fees. r10..r120 = minutes after the flag; r_close = 16:00 ET; r_end = end of the extended session; mfe / mae = best / worst price reached the same day.

## Flags

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scan: social only | 18 | -0.0 ± 0.7 | -1.9 ± 1.0 | -2.5 ± 1.3 | -3.5 ± 1.3 | -4.2 ± 1.7 | -4.6 ± 1.8 | -2.6 ± 2.3 | -6.5 ± 2.7 | +4.1 ± 1.0 | -8.3 ± 2.0 |
| scan: social+vol | 101 | +0.4 ± 0.5 | +0.6 ± 1.0 | +1.8 ± 1.2 | +0.5 ± 1.0 | +1.6 ± 1.7 | -0.1 ± 1.7 | -0.4 ± 1.8 | -2.9 ± 2.3 | +16.4 ± 2.6 | -9.5 ± 1.0 |
| scan: momentum | 23 | +2.0 ± 2.4 | +1.8 ± 4.0 | -2.2 ± 3.3 | -4.0 ± 3.5 | -1.7 ± 3.9 | -4.8 ± 3.6 | -2.0 ± 5.8 | -0.8 ± 7.2 | +15.3 ± 5.4 | -12.9 ± 2.8 |
| watcher: tier2 | 343 | +0.0 ± 0.3 | -0.8 ± 0.4 | -0.9 ± 0.4 | -0.9 ± 0.5 | -0.2 ± 0.9 | -0.7 ± 0.9 | +3.3 ± 4.2 | +7.0 ± 9.4 | +12.5 ± 1.2 | -9.5 ± 0.5 |
| watcher: momentum | 36 | +0.4 ± 1.4 | +0.1 ± 1.8 | -0.4 ± 1.6 | -2.1 ± 1.6 | +0.0 ± 3.1 | -0.5 ± 3.7 | +39.0 ± 44.0 | +87.8 ± 100.3 | +21.0 ± 5.3 | -13.2 ± 1.5 |

## Control: random watchlist stocks at the same moments

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scan: social only | 180 | -0.1 ± 0.1 | -0.2 ± 0.2 | -0.2 ± 0.2 | -0.1 ± 0.3 | -0.3 ± 0.5 | -0.0 ± 0.5 | -0.0 ± 0.9 | -0.3 ± 1.2 | +4.4 ± 0.5 | -4.0 ± 0.4 |
| scan: social+vol | 1010 | -0.1 ± 0.1 | -0.0 ± 0.2 | -0.0 ± 0.2 | -0.0 ± 0.2 | +0.1 ± 0.3 | +0.1 ± 0.4 | -0.1 ± 0.4 | -1.4 ± 0.4 | +5.6 ± 0.8 | -4.1 ± 0.2 |
| scan: momentum | 230 | +0.1 ± 0.1 | +0.1 ± 0.2 | +0.0 ± 0.2 | +0.5 ± 0.5 | -0.0 ± 0.4 | -0.2 ± 0.3 | +0.4 ± 0.5 | -0.3 ± 0.6 | +4.6 ± 0.7 | -3.3 ± 0.3 |
| watcher: tier2 | 3430 | +0.0 ± 0.0 | -0.0 ± 0.1 | -0.2 ± 0.1 | -0.2 ± 0.1 | -0.4 ± 0.1 | -0.3 ± 0.1 | -0.6 ± 0.1 | -1.2 ± 0.4 | +4.7 ± 0.2 | -4.1 ± 0.1 |
| watcher: momentum | 360 | -0.1 ± 0.1 | -0.1 ± 0.2 | -0.2 ± 0.2 | -0.2 ± 0.2 | -0.1 ± 0.4 | -0.4 ± 0.3 | -0.5 ± 0.4 | -0.1 ± 0.9 | +4.3 ± 0.4 | -4.1 ± 0.3 |

## Flags, first and second half of the period

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scan: social only — first half of days | 6 | -0.5 ± 1.1 | -3.0 ± 2.2 | -5.9 ± 3.5 | -5.5 ± 3.2 | -5.1 ± 3.9 | -6.5 ± 4.6 | -2.7 ± 4.6 | -10.1 ± 4.3 | +7.1 ± 2.4 | -11.8 ± 4.5 |
| scan: social only — second half of days | 12 | +0.2 ± 0.8 | -1.3 ± 1.1 | -0.8 ± 0.7 | -2.5 ± 1.0 | -3.6 ± 1.5 | -3.7 ± 1.7 | -2.5 ± 2.5 | -3.8 ± 3.3 | +2.5 ± 0.7 | -6.5 ± 1.9 |

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scan: social+vol — first half of days | 47 | -0.3 ± 0.8 | -1.0 ± 1.0 | -0.2 ± 1.1 | -1.3 ± 1.4 | -0.6 ± 2.5 | -1.7 ± 2.4 | -0.8 ± 2.7 | +0.7 ± 3.7 | +10.6 ± 2.5 | -9.8 ± 1.5 |
| scan: social+vol — second half of days | 54 | +1.0 ± 0.6 | +2.0 ± 1.6 | +3.6 ± 1.9 | +2.1 ± 1.4 | +3.6 ± 2.2 | +1.4 ± 2.5 | -0.0 ± 2.4 | -6.6 ± 2.5 | +21.4 ± 4.2 | -9.3 ± 1.3 |

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scan: momentum — first half of days | 15 | +4.6 ± 3.2 | +4.6 ± 5.6 | -0.6 ± 4.3 | -3.1 ± 4.8 | -1.9 ± 5.9 | -4.6 ± 5.0 | -1.5 ± 8.6 | +3.1 ± 10.6 | +19.6 ± 8.0 | -13.7 ± 3.6 |
| scan: momentum — second half of days | 8 | -2.8 ± 2.9 | -3.5 ± 4.8 | -5.0 ± 5.2 | -5.8 ± 4.7 | -1.3 ± 3.4 | -5.2 ± 5.2 | -3.0 ± 5.3 | -8.0 ± 6.2 | +7.2 ± 2.8 | -11.4 ± 4.8 |

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| watcher: tier2 — first half of days | 137 | -0.4 ± 0.4 | -1.8 ± 0.6 | -1.8 ± 0.6 | -1.8 ± 0.8 | -1.7 ± 1.2 | -2.2 ± 1.2 | -2.6 ± 1.3 | -1.5 ± 1.8 | +11.0 ± 1.3 | -10.5 ± 0.8 |
| watcher: tier2 — second half of days | 206 | +0.3 ± 0.3 | -0.1 ± 0.5 | -0.3 ± 0.4 | -0.2 ± 0.6 | +0.8 ± 1.2 | +0.3 ± 1.2 | +7.8 ± 7.3 | +13.3 ± 16.4 | +13.4 ± 1.7 | -8.9 ± 0.5 |

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| watcher: momentum — first half of days | 13 | +0.4 ± 1.5 | -0.2 ± 2.0 | +1.0 ± 3.1 | -1.9 ± 3.7 | -5.7 ± 4.6 | -2.6 ± 6.4 | -5.7 ± 5.6 | -11.5 ± 6.7 | +17.5 ± 6.2 | -15.6 ± 3.3 |
| watcher: momentum — second half of days | 23 | +0.4 ± 2.1 | +0.2 ± 2.7 | -1.1 ± 1.8 | -2.2 ± 1.6 | +3.3 ± 4.1 | +0.7 ± 4.6 | +69.5 ± 73.9 | +155.7 ± 168.9 | +22.9 ± 7.5 | -11.9 ± 1.3 |

## The spikes themselves (day high ≥ +50%): buying the close of the first 5-minute bar at +20%

184 spikes. Median time from there to the day's high: 122 minutes. Share still above the entry at the end of the day: 45%; at the next day's close: 31%.

| group | n | r10 | r30 | r60 | r120 | r_close | r_end | r_next_open | r_next_close | mfe | mae |
|---|---|---|---|---|---|---|---|---|---|---|---|
| starts in regular hours | 73 | +1.6 ± 1.8 | +2.0 ± 3.2 | +0.2 ± 3.7 | -0.7 ± 3.5 | +6.4 ± 4.2 | +4.4 ± 4.3 | +5.5 ± 5.8 | +8.5 ± 6.5 | +49.7 ± 5.6 | -20.1 ± 2.2 |
| starts post-market | 9 | +7.3 ± 5.0 | +10.6 ± 3.0 | +12.6 ± 3.2 | +10.9 ± 5.5 | n/a | +12.3 ± 6.4 | -6.5 ± 6.5 | -1.2 ± 12.1 | +30.6 ± 4.0 | -11.3 ± 2.9 |
| starts pre-market | 102 | +1.2 ± 1.6 | -0.5 ± 2.0 | -0.6 ± 2.1 | +0.6 ± 3.4 | -5.3 ± 3.1 | -5.6 ± 3.5 | -9.1 ± 4.2 | -15.6 ± 3.7 | +52.3 ± 5.8 | -27.5 ± 2.0 |
