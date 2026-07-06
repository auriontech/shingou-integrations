"""Shingou sentiment overlay for Jesse (live/paper trading).

Same shape as the Freqtrade example: an SMA-cross base strategy with the
Shingou signal as entry FILTER, SIZING input and event KILL-SWITCH. The
`_refresh_shingou` / `_entry_allowed` / sizing pieces are what you copy into
your own strategy.

Quickstart:
  1. Free API key: https://shingou.io/dashboard
  2. export SHINGOU_API_KEY=sk_...
  3. Put this file in your Jesse project's strategies/ShingouFilter/__init__.py
     and select it for a live/paper route on the 1h timeframe.

IMPORTANT — backtesting: this strategy fetches the LIVE signal, so Jesse
backtests would see today's sentiment on historical candles (lookahead). For
honest research, pre-download point-in-time history from /v1/history/sentiment
(every bucket carries as-of timestamps) and join it to your candles instead.
Measured live performance, negative results included:
https://shingou.io/research
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from jesse.strategies import Strategy
from jesse import utils

API_BASE = os.environ.get("SHINGOU_API_BASE", "https://api.shingou.io/v1")
USER_AGENT = "shingou-jesse/0.1.0"
KILL_EVENTS = {"hack_exploit", "regulation", "delisting"}
KILL_WINDOW = timedelta(hours=24)
# Base tickers whose venue name differs from the Shingou symbol; everything
# else maps BASE -> "{BASE}-USD". Full table: ../shared/symbol-map.json
BASE_ALIASES = {"XBT": "BTC", "RENDER": "RNDR"}


def shingou_symbol(jesse_symbol: str) -> str:
    """'BTC-USDT' -> 'BTC-USD' (quote currency is irrelevant to the signal)."""
    base = jesse_symbol.split("-")[0].upper()
    return f"{BASE_ALIASES.get(base, base)}-USD"


class ShingouFilter(Strategy):
    def __init__(self):
        super().__init__()
        self._signal: dict | None = None
        self._events: list = []
        self._bucket: datetime | None = None

    # ── Shingou client (one refresh per hour bucket) ────────────────────────

    def _headers(self) -> dict:
        key = os.environ.get("SHINGOU_API_KEY", "")
        if not key:
            raise RuntimeError("Set SHINGOU_API_KEY — free key at https://shingou.io/dashboard")
        return {"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT}

    def _refresh_shingou(self) -> None:
        now = datetime.now(timezone.utc)
        bucket = now.replace(minute=0, second=0, microsecond=0)
        if bucket == self._bucket:
            return
        symbol = shingou_symbol(self.symbol)
        try:
            resp = requests.get(
                f"{API_BASE}/sentiment",
                params={"symbols": symbol},
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            self._signal = data[0] if data else None

            resp = requests.get(
                f"{API_BASE}/events",
                params={"symbol": symbol, "limit": 20},
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            self._events = resp.json().get("events", [])
            self._bucket = bucket  # only advance on success so failures retry
        except Exception as err:
            self.log(f"Shingou refresh failed (keeping last snapshot): {err}")

    def _kill_event(self) -> str | None:
        now = datetime.now(timezone.utc)
        for event in self._events:
            if event.get("event_type") not in KILL_EVENTS:
                continue
            occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            if now - occurred <= KILL_WINDOW:
                return event["event_type"]
        return None

    def _entry_allowed(self) -> bool:
        kill = self._kill_event()
        if kill:
            self.log(f"Shingou kill-switch: standing aside ({kill} within 24h)")
            return False
        if self._signal is None:
            # Fail-open: a signal outage should not silently stop the base
            # strategy. Flip to False if you prefer fail-closed.
            return True
        if self._signal["direction"] == "bearish":
            self.log(
                f"Shingou filter: bearish (score={self._signal['score']:.2f}, "
                f"confidence={self._signal['confidence']:.2f}) — skipping entry"
            )
            return False
        return True

    # ── Base strategy: plain SMA cross (replace with your own) ──────────────

    @property
    def sma_fast(self):
        return utils.sma(self.candles[:, 2], 12)

    @property
    def sma_slow(self):
        return utils.sma(self.candles[:, 2], 26)

    def before(self) -> None:
        self._refresh_shingou()

    def should_long(self) -> bool:
        return self.sma_fast > self.sma_slow and self._entry_allowed()

    def should_short(self) -> bool:
        return False

    def go_long(self) -> None:
        # Confidence-scaled sizing: 50% of the risk budget at confidence 0,
        # 100% at confidence 1 (only when a bullish signal is present).
        fraction = 0.5
        if self._signal and self._signal["direction"] == "bullish":
            fraction = 0.5 + 0.5 * float(self._signal["confidence"])
        qty = utils.size_to_qty(self.balance * 0.1 * fraction, self.price)
        self.buy = qty, self.price
        self.stop_loss = qty, self.price * 0.95
        self.take_profit = qty, self.price * 1.10

    def update_position(self) -> None:
        if self.sma_fast < self.sma_slow:
            self.liquidate()

    def should_cancel_entry(self) -> bool:
        return True
