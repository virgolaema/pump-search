"""Real-time alerts for strong flags (volume burst + StockTwits signal in the same run).

Sends an ntfy.sh push (NTFY_TOPIC) and opens a GitHub issue (GitHub emails the repo owner).
Run `python -m pump.alerts --test` to send a test alert."""
import os
import sys

import requests

from .common import ALERTS, append_csv, now_utc


def is_strong(reasons):
    return "vol_burst" in reasons and "st_" in reasons


def _ntfy(title, body, url):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return "no topic"
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode(), timeout=10,
                          headers={"Title": title, "Tags": "chart_with_upwards_trend", "Click": url, "Priority": "high"})
        return f"http_{r.status_code}"
    except Exception as e:
        return f"error:{type(e).__name__}"


def _issue(title, body):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return "no token"
    try:
        r = requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=10,
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                          json={"title": title, "body": body, "labels": ["alert"]})
        return f"http_{r.status_code}"
    except Exception as e:
        return f"error:{type(e).__name__}"


def send(flags):
    """flags: DataFrame rows from collect with ticker, price, pct, reasons, ts."""
    import pandas as pd
    out = []
    for r in flags.itertuples():
        title = f"Pump watch: {r.ticker} ${r.price:.2f} ({r.pct:+.0f}%)"
        body = (f"{r.ticker} at ${r.price:.2f}, {r.pct:+.1f}% vs previous close, {r.ts}.\n"
                f"Signals: {r.reasons}.\n"
                f"Paper test only: a hit means +30% within 2 trading days; most flags are not hits.")
        url = f"https://finance.yahoo.com/quote/{r.ticker}"
        out.append({"ts": r.ts, "ticker": r.ticker, "ntfy": _ntfy(title, body, url),
                    "issue": _issue(title, body + f"\n\n{url}")})
    if out:
        append_csv(ALERTS, pd.DataFrame(out))
    return out


if __name__ == "__main__" and "--test" in sys.argv:
    import pandas as pd
    t = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    res = send(pd.DataFrame([{"ts": t, "ticker": "TEST", "price": 1.0, "pct": 0.0,
                              "reasons": "test alert, ignore"}]))
    print(res)
