# Shingou × Freqtrade

An example [Freqtrade](https://www.freqtrade.io) strategy using the Shingou sentiment
signal as an **entry filter**, **position-sizing input** and **event kill-switch** on top
of a plain EMA-cross base strategy. The overlay hooks are the part to copy into your own
strategy — the EMA cross is just a stand-in.

## Quickstart (~5 minutes)

```bash
# 1. Get a free API key (no card): https://shingou.io/dashboard
export SHINGOU_API_KEY=sk_...

# 2. Drop the strategy into your bot
cp ShingouSentiment.py user_data/strategies/

# 3. Dry-run it
freqtrade trade --strategy ShingouSentiment --dry-run
```

Works with any USDT/USD/USDC quote pairs of the [30 supported
assets](../shared/symbol-map.json) — the strategy maps `BTC/USDT` → `BTC-USD` itself.

## What it does

| Hook | Behavior |
| --- | --- |
| `bot_loop_start` | Once per hour bucket: one `/v1/sentiment` call for the whole whitelist + one `/v1/events` call per symbol. |
| `confirm_trade_entry` | Skips entries when the signal is `bearish`, and for 24h after a `hack_exploit` / `regulation` / `delisting` event. Fails **open** on signal outage (documented in code; flip one line for fail-closed). |
| `custom_stake_amount` | Scales stake by confidence: 50% at confidence 0 → 100% at confidence 1 (only when bullish). |

Quota math: a 10-pair hourly bot ≈ 264 requests/day, well inside the free tier
(1,000/day, 30/min). Free keys are live on BTC/ETH/SOL and 24h-delayed elsewhere —
the paid plan removes the delay.

## Honesty notes

- Pooled hit rate of the raw signal is ~a coin flip and we publish that — the value is
  event-conditional (see [shingou.io/research](https://shingou.io/research)). That is
  exactly why this example only filters/sizes and never generates entries.
- Freqtrade **backtests cannot see point-in-time sentiment** with this strategy (it
  fetches live). For honest backtests, join your candles against
  `/v1/history/sentiment` (as-of timestamps, no lookahead) instead of replaying live
  fetches.
- The strategy sends `User-Agent: shingou-freqtrade/0.1.0` so installs are attributable
  per channel. The code is ~200 lines — audit it; nothing but the key and symbols leaves.

*Not investment advice. Dry-run first; backtest before risking anything.*
