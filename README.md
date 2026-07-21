# Shingou integrations

Free, open-source clients that render the [Shingou](https://shingou.io) sentiment signal
inside the tools day traders already use. Every integration works instantly with a
**free API key** ([shingou.io/dashboard](https://shingou.io/dashboard)) — the paid key is
what removes the 24h delay outside the live majors.

| Folder | Platform | Status |
| --- | --- | --- |
| [`freqtrade/`](freqtrade/) | [Freqtrade](https://www.freqtrade.io) crypto bot (Python) | ✅ ready |
| [`jesse/`](jesse/) | [Jesse](https://jesse.trade) research/trading framework (Python) | ✅ ready |
| `ninjatrader/`, `metatrader5/`, … | Chart-platform indicators | planned — see the [roadmap](https://shingou.io/docs) |

## What the signal is (and is not)

One signal per asset per hour: `score ∈ [-1, 1]`, `confidence ∈ [0, 1]`, a
`direction` call, dominant `event` types, and the source articles behind it.
Measured performance — including the negative results — is published at
[shingou.io/research](https://shingou.io/research). The honest way to use an hourly
news signal, and the only way these examples use it:

- **Filter** — skip entries your base strategy would take against the signal.
- **Sizing** — scale stake by confidence.
- **Kill-switch** — stand aside after `hack_exploit` / `regulation` / `delisting` events.

Never as an entry generator on its own.

## The common client contract

All integrations in this repo follow the same rules, so you can audit exactly what runs:

- **Auth**: the API key comes from user configuration (env var / platform settings) —
  never hardcoded, never logged, sent only to `api.shingou.io`.
- **Data pattern**: fetch `/v1/sentiment` once per hour bucket for all needed symbols in
  one call; poll nothing faster. This stays far inside the free tier
  (1,000 requests/day, 30/min burst).
- **Symbol mapping**: platform ticker → Shingou symbol via
  [`shared/symbol-map.json`](shared/symbol-map.json) (base asset → `X-USD`).
- **Attribution**: every client sends `User-Agent: shingou-<platform>/<version>` — that
  is the whole telemetry story; the code is public so you can verify nothing else leaves.
- **Honesty markers**: `reconstructed: true` buckets and free-tier delays are surfaced,
  not hidden.

## Alerts: Telegram (no code)

A free public feed of the Shingou signal: direction flips on supported pairs and
high-severity typed events (hacks, regulation, delistings, legal). It is
deliberately quiet, roughly ten high-conviction alerts a day, and every alert
carries its source links so you can judge the story yourself.

- **Telegram:** [t.me/shingou_alerts](https://t.me/shingou_alerts)

Under the hood it is a tiny hourly worker reading the same public API you can
call (`/v1/sentiment` for flips, `/v1/events` for the typed stream) and pushing
whatever clears a confidence floor. Nothing in the feed is trade advice. It
exists so you can watch the indicator work before wiring the API into your own
strategy (see the Freqtrade and Jesse examples above).

## License

MIT — see [LICENSE](LICENSE). The integrations are free distribution; the subscription
is the data. API usage is governed by the [Shingou terms](https://shingou.io/terms)
(commercial use included on paid plans; free tier is for personal/evaluation use).

*Not investment advice. These are example integrations of a signal layer, not trading
recommendations; backtest before risking anything.*
