# Shingou × Jesse

An example [Jesse](https://jesse.trade) strategy using the Shingou sentiment signal as an
**entry filter**, **sizing input** and **event kill-switch** on top of a plain SMA-cross
base strategy — for **live/paper routes**. The `_refresh_shingou` / `_entry_allowed` /
sizing pieces are what you copy into your own strategy.

## Quickstart

```bash
# 1. Free API key (no card): https://shingou.io/dashboard
export SHINGOU_API_KEY=sk_...

# 2. Add the strategy
mkdir -p strategies/ShingouFilter
cp ShingouFilter.py strategies/ShingouFilter/__init__.py

# 3. Route it (routes.py) on the 1h timeframe, then run live/paper.
```

## Backtesting honestly

This strategy fetches the **live** signal once per hour bucket, so running it in Jesse's
backtester would apply today's sentiment to historical candles — lookahead bias. For
research, pre-download point-in-time history instead (every bucket carries as-of
timestamps; free tier: 7 days, starter: 90):

```python
r = requests.get(
    "https://api.shingou.io/v1/history/sentiment",
    params={"symbol": "BTC-USD", "from": "2026-06-01T00:00:00Z",
            "to": "2026-06-30T00:00:00Z", "interval": "1h"},
    headers={"Authorization": f"Bearer {KEY}", "User-Agent": "shingou-jesse/0.1.0"},
)
```

and join it to your candles by bucket. Measured live performance — negative results
included — is published at [shingou.io/research](https://shingou.io/research).

## Notes

- Quota: 2 requests per symbol per hour ≈ 48/day per route — far inside the free tier
  (1,000/day). Free keys are live on BTC/ETH/SOL, 24h-delayed elsewhere.
- Sends `User-Agent: shingou-jesse/0.1.0` (channel attribution). The code is short —
  audit it; nothing but the key and the symbol leaves your machine.

*Not investment advice. Paper-trade first.*
