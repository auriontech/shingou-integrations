"""Shingou sentiment overlay for Freqtrade.

A deliberately simple EMA-cross base strategy with the Shingou signal used the
only way an hourly news signal honestly can be: as an entry FILTER, a
position-SIZING input and an event KILL-SWITCH — never as an entry generator.
Swap the EMA logic for your own strategy; the three overlay hooks
(`confirm_trade_entry`, `custom_stake_amount`, `bot_loop_start`) are the part
worth copying.

Quickstart (about 5 minutes):
  1. Free API key: https://shingou.io/dashboard
  2. export SHINGOU_API_KEY=sk_...
  3. Copy this file into user_data/strategies/ and run:
     freqtrade trade --strategy ShingouSentiment

Quota: one /v1/sentiment call per hour for the whole whitelist plus one
/v1/events call per symbol per hour — a 10-pair bot uses ~264 requests/day of
the free tier's 1,000. Free keys get live signals on BTC/ETH/SOL and
24h-delayed signals elsewhere (the strategy still works; paid removes the
delay). Measured signal performance, negative results included:
https://shingou.io/research
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from pandas import DataFrame

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("SHINGOU_API_BASE", "https://api.shingou.io/v1")
USER_AGENT = "shingou-freqtrade/0.1.0"

# Stand aside for a day after these event types — an hourly news signal's most
# defensible job is knowing when NOT to trade.
KILL_EVENTS = {"hack_exploit", "regulation", "delisting"}
KILL_WINDOW = timedelta(hours=24)

# Base tickers whose venue name differs from the Shingou symbol; everything
# else maps BASE -> "{BASE}-USD". Full table: ../shared/symbol-map.json
BASE_ALIASES = {"XBT": "BTC", "RENDER": "RNDR"}


def shingou_symbol(pair: str) -> str:
    """'BTC/USDT:USDT' -> 'BTC-USD' (quote currency is irrelevant to the signal)."""
    base = pair.split("/")[0].split(":")[0].upper()
    return f"{BASE_ALIASES.get(base, base)}-USD"


class ShingouSentiment(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    process_only_new_candles = True
    startup_candle_count = 30
    can_short = False

    minimal_roi = {"0": 0.10}
    stoploss = -0.05

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._signals: dict[str, dict] = {}
        self._events: dict[str, list] = {}
        self._bucket: datetime | None = None

    # ── Shingou client (one bucketed refresh per hour) ──────────────────────

    def _headers(self) -> dict[str, str]:
        key = os.environ.get("SHINGOU_API_KEY", "")
        if not key:
            raise RuntimeError("Set SHINGOU_API_KEY — free key at https://shingou.io/dashboard")
        return {"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT}

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        bucket = current_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if bucket == self._bucket:
            return

        symbols = sorted({shingou_symbol(p) for p in self.dp.current_whitelist()})
        try:
            resp = requests.get(
                f"{API_BASE}/sentiment",
                params={"symbols": ",".join(symbols)},
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            self._signals = {s["symbol"]: s for s in resp.json().get("data", [])}
            self._bucket = bucket  # only advance on success so failures retry next loop
        except Exception as err:
            logger.warning("Shingou sentiment refresh failed (keeping last snapshot): %s", err)
            return

        for symbol in symbols:
            try:
                resp = requests.get(
                    f"{API_BASE}/events",
                    params={"symbol": symbol, "limit": 20},
                    headers=self._headers(),
                    timeout=10,
                )
                resp.raise_for_status()
                self._events[symbol] = resp.json().get("events", [])
            except Exception as err:
                logger.warning("Shingou events refresh failed for %s: %s", symbol, err)

    def _kill_event(self, symbol: str, now: datetime) -> str | None:
        for event in self._events.get(symbol, []):
            if event.get("event_type") not in KILL_EVENTS:
                continue
            occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            if now - occurred <= KILL_WINDOW:
                return event["event_type"]
        return None

    # ── Base strategy: plain EMA cross (replace with your own) ──────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = dataframe["close"].ewm(span=12, adjust=False).mean()
        dataframe["ema_slow"] = dataframe["close"].ewm(span=26, adjust=False).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1)),
            "exit_long",
        ] = 1
        return dataframe

    # ── The Shingou overlay: filter, kill-switch, sizing ────────────────────

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        symbol = shingou_symbol(pair)
        now = current_time.astimezone(timezone.utc)

        kill = self._kill_event(symbol, now)
        if kill:
            logger.info("Shingou kill-switch: skipping %s entry (%s within 24h)", pair, kill)
            return False

        signal = self._signals.get(symbol)
        if signal is None:
            # Fail-open: a signal outage should not silently stop the base
            # strategy. Flip to `return False` if you prefer fail-closed.
            logger.info("No Shingou signal for %s — allowing base-strategy entry", symbol)
            return True
        if signal["direction"] == "bearish":
            logger.info(
                "Shingou filter: skipping %s entry (bearish, score=%.2f, confidence=%.2f)",
                pair,
                signal["score"],
                signal["confidence"],
            )
            return False
        return True

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        signal = self._signals.get(shingou_symbol(pair))
        if not signal or signal["direction"] != "bullish":
            return proposed_stake
        # Confidence-scaled sizing: 50% stake at confidence 0, full at 1.
        scaled = proposed_stake * (0.5 + 0.5 * float(signal["confidence"]))
        return max(min_stake or 0.0, min(scaled, max_stake))
