# Do SEC filings predict which spikes fade?

Trades with filings data: 1343 of 1347 (tickers covered: 99%). Exit: +50% / -50% / next-day close; ret = return on the trade after 1% slippage each way. Features use only filings accepted before entry. Seven features fixed in advance; |t| above about 2.7 would be needed to take one seriously.

## Group: control (920 trades, avg return -3.0%)

| feature | trades with | avg with | avg without | difference | t | with feature: +50% hits | first half diff | second half diff |
|---|---|---|---|---|---|---|---|---|
| offering | 159 | -5.8% | -2.4% | -3.5 pts | -1.4 | 15% | -1.2 | -5.9 |
| shelf | 145 | +1.0% | -3.7% | +4.7 pts | +1.7 | 24% | +7.1 | +2.5 |
| financing | 184 | -6.6% | -2.0% | -4.6 pts | -1.9 | 14% | -8.0 | -1.5 |
| charter | 181 | -4.3% | -2.6% | -1.7 pts | -0.7 | 18% | -11.8 | +6.5 |
| late | 149 | -6.1% | -2.4% | -3.7 pts | -1.5 | 15% | -5.0 | -2.4 |
| fresh8k | 113 | -3.3% | -2.9% | -0.4 pts | -0.1 | 14% | +0.5 | -1.3 |
| dilution | 415 | -3.2% | -2.8% | -0.4 pts | -0.2 | 18% | -2.0 | +1.2 |

P&L at $100 per trade: all 920 trades $-2,721; without dilution-flagged trades (505) $-1,408 (avg -2.8%); only dilution-flagged (415) $-1,313 (avg -3.2%).

## Group: tier2 (423 trades, avg return -3.2%)

| feature | trades with | avg with | avg without | difference | t | with feature: +50% hits | first half diff | second half diff |
|---|---|---|---|---|---|---|---|---|
| offering | 83 | -4.2% | -2.9% | -1.2 pts | -0.4 | 17% | +3.2 | -5.6 |
| shelf | 64 | +0.9% | -3.9% | +4.8 pts | +1.2 | 22% | +9.8 | +0.6 |
| financing | 77 | -8.3% | -2.0% | -6.2 pts | -2.0 | 9% | -9.6 | -3.8 |
| charter | 76 | -2.1% | -3.4% | +1.3 pts | +0.4 | 18% | -4.3 | +5.5 |
| late | 63 | +1.0% | -3.9% | +4.8 pts | +1.3 | 19% | +2.2 | +7.0 |
| fresh8k | 53 | +0.5% | -3.7% | +4.2 pts | +1.1 | 17% | +2.8 | +6.1 |
| dilution | 189 | -2.0% | -4.1% | +2.2 pts | +0.8 | 17% | +2.3 | +2.0 |

P&L at $100 per trade: all 423 trades $-1,341; without dilution-flagged trades (234) $-968 (avg -4.1%); only dilution-flagged (189) $-373 (avg -2.0%).
