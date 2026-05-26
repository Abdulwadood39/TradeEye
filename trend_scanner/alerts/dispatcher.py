"""
dispatcher.py — Modular alert dispatcher for external communication platforms.

Routing logic:
  - Confirmed trend (is_trending AND not veto_killed)  → Telegram + Discord (trends channel)
  - Veto killed (passed signals but killed by gate)    → Discord Vetos channel
  - No trend (never reached signal threshold)          → Discord No-Trend channel

All channels are enabled/disabled via scanner.toml [notifications.*] or profiles.
"""
from __future__ import annotations

import logging
import requests
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendResult

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    """Base interface for all notification platforms."""

    @abstractmethod
    def send_alert(self, result: TrendResult) -> bool:
        """Send a rich trend alert. Returns True if successful."""
        pass

    @abstractmethod
    def send_message(self, text: str, timeframe: str = None) -> bool:
        """Send a plain text message. Returns True if successful."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────

class TelegramPlatform(BasePlatform):
    """Sends trend alerts to a Telegram chat."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_ids = [cid.strip() for cid in chat_id.split(',')] if chat_id else []

    def send_alert(self, result: TrendResult) -> bool:
        if not self.token or not self.chat_ids:
            logger.warning("  ⚠️  Telegram token or chat_id(s) missing. Cannot send alert.")
            return False

        message = (
            f"*{result.emoji} {result.direction_label} Alert: {result.ticker}*\n"
            f"• Timeframe: {result.timeframe}\n"
            f"• Score: {result.score}/5\n"
            f"• Confidence: {result.confidence:.0%}\n"
        )
        if result.vlm_verdict:
            message += f"• VLM: {result.vlm_verdict}\n"

        url = f"https://api.telegram.org/bot{self.token}/"
        chart_path = result.chart_path or result.chart_1h_path or result.chart_1d_path
        success = True

        for cid in self.chat_ids:
            try:
                if chart_path:
                    with open(chart_path, 'rb') as photo:
                        resp = requests.post(
                            url + "sendPhoto",
                            data={"chat_id": cid, "caption": message, "parse_mode": "Markdown"},
                            files={"photo": photo},
                            timeout=30,
                        )
                else:
                    resp = requests.post(
                        url + "sendMessage",
                        data={"chat_id": cid, "text": message, "parse_mode": "Markdown"},
                        timeout=30,
                    )
                resp.raise_for_status()
                logger.info(f"  📩 Telegram alert sent for {result.ticker} [{result.timeframe}] to {cid}")
            except Exception as e:
                logger.error(f"  ❌ Failed to send Telegram alert to {cid}: {e}")
                success = False
        return success

    def send_message(self, text: str, timeframe: str = None) -> bool:
        if not self.token or not self.chat_ids:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        success = True
        for cid in self.chat_ids:
            try:
                resp = requests.post(
                    url,
                    data={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                    timeout=30,
                )
                resp.raise_for_status()
                logger.info(f"  📩 Telegram message sent to {cid}")
            except Exception as e:
                logger.error(f"  ❌ Failed to send Telegram message to {cid}: {e}")
                success = False
        return success


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD — Base
# ─────────────────────────────────────────────────────────────────────────────

class DiscordPlatform(BasePlatform):
    """
    Sends trend alerts to a Discord webhook (confirmed trends only).
    """

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.msg_ids_file = "trend_scanner/output/discord_msg_ids.txt"

    def _build_message(self, result: TrendResult) -> str:
        message = (
            f"**{result.emoji} {result.direction_label}: {result.ticker}**\n"
            f"• Timeframe: {result.timeframe}\n"
            f"• Score: {result.score}/5\n"
            f"• Confidence: {result.confidence:.0%}\n"
        )
        if result.vlm_verdict:
            message += f"• VLM: {result.vlm_verdict}\n"
        return message

    def _post(self, message: str, chart_path: str | None, timeframe: str | None, label: str) -> bool:
        if not self.webhook_url:
            logger.warning(f"  \u26a0\ufe0f  Discord webhook_url missing for {label}.")
            return False
        url = self.webhook_url + "?wait=true"
        for attempt in range(4):   # up to 4 attempts with retry-after back-off
            try:
                if chart_path:
                    with open(chart_path, 'rb') as photo:
                        resp = requests.post(url, data={"content": message}, files={"file": photo}, timeout=30)
                else:
                    resp = requests.post(url, json={"content": message}, timeout=30)

                if resp.status_code == 429:
                    retry_after = float(resp.json().get("retry_after", 2.0))
                    logger.warning(f"  \u23f3 Discord rate-limited [{label}], retrying in {retry_after:.1f}s")
                    time.sleep(retry_after + 0.1)
                    continue

                resp.raise_for_status()
                self._save_msg_id(resp, timeframe)
                logger.info(f"  \U0001f4e9 Discord [{label}] sent")
                return True

            except Exception as e:
                logger.error(f"  \u274c Failed to send Discord [{label}] (attempt {attempt + 1}): {e}")
                if attempt < 3:
                    time.sleep(1.5)
        return False


    def _save_msg_id(self, resp: requests.Response, timeframe: str | None):
        try:
            msg_id = resp.json().get("id")
            if msg_id:
                import os
                os.makedirs(os.path.dirname(self.msg_ids_file), exist_ok=True)
                with open(self.msg_ids_file, "a") as f:
                    tf_str = f"|{timeframe}" if timeframe else ""
                    f.write(f"{self.webhook_url}|{msg_id}{tf_str}\n")
        except Exception as e:
            logger.warning(f"  ⚠️ Could not save Discord message ID: {e}")

    def send_alert(self, result: TrendResult) -> bool:
        chart_path = result.chart_path or result.chart_1h_path or result.chart_1d_path
        return self._post(
            message=self._build_message(result),
            chart_path=chart_path,
            timeframe=result.timeframe,
            label="TREND",
        )

    def send_message(self, text: str, timeframe: str = None) -> bool:
        return self._post(message=text, chart_path=None, timeframe=timeframe, label="MSG")


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD VETOS CHANNEL
# ─────────────────────────────────────────────────────────────────────────────

class DiscordVetosPlatform(DiscordPlatform):
    """
    Sends alerts for signals that were VETOED (passed scoring but killed by a gate).
    Useful for monitoring what would have fired without veto filtering.
    Configured via: [notifications.discord_vetos] in scanner.toml
    Env var: DISCORD_VETOS_WEBHOOK_URL
    """

    def send_alert(self, result: TrendResult) -> bool:
        # Find which veto gate(s) failed
        failed_vetos = [
            s.name for s in result.signals
            if getattr(s, "is_veto", False) and not s.passed
        ]
        veto_names = ", ".join(failed_vetos) if failed_vetos else "unknown"

        message = (
            f"**🛑 VETOED: {result.ticker}** [{result.timeframe}]\n"
            f"• Would have been: {result.initial_direction.upper()}\n"
            f"• Signal Score: {result.score}/5\n"
            f"• Vetoed by: {veto_names}\n"
        )
        # Add veto scores for quick diagnosis
        for s in result.signals:
            if getattr(s, "is_veto", False):
                icon = "✅" if s.passed else "❌"
                message += f"  {icon} {s.name}: {s.score:.3f}\n"

        chart_path = result.chart_path or result.chart_1h_path or result.chart_1d_path
        return self._post(
            message=message,
            chart_path=chart_path,
            timeframe=result.timeframe,
            label="VETO",
        )

    def send_message(self, text: str, timeframe: str = None) -> bool:
        return self._post(message=text, chart_path=None, timeframe=timeframe, label="VETO-MSG")


# ─────────────────────────────────────────────────────────────────────────────
# DISCORD NO-TREND CHANNEL
# ─────────────────────────────────────────────────────────────────────────────

class DiscordNoTrendPlatform(DiscordPlatform):
    """
    Batches all no-trend results for a timeframe and sends ONE message per scan.

    Sends individually per ticker causes Discord 429 rate-limit storms when the
    watchlist is large. Instead we buffer results during the scan and flush a
    single consolidated message (with the best available chart attached) at the
    end via AlertDispatcher.flush_no_trend_batch().

    Configured via: [notifications.discord_no_trend] in scanner.toml
    Env var: DISCORD_NO_TREND_WEBHOOK_URL
    """

    def __init__(self, webhook_url: str):
        super().__init__(webhook_url)
        # buffer: {timeframe: [TrendResult, ...]}
        self._buffer: Dict[str, list] = {}

    def send_alert(self, result: "TrendResult") -> bool:
        """Buffer the result — do NOT send immediately. Call flush_batch() after scan."""
        tf = result.timeframe
        if tf not in self._buffer:
            self._buffer[tf] = []
        self._buffer[tf].append(result)
        return True   # optimistically true; actual send happens at flush

    def flush_batch(self, timeframe: str) -> bool:
        """
        Send one consolidated message for all buffered no-trend results for
        this timeframe, then clear the buffer.
        Attaches a chart from the last result that has one (if any).
        """
        results = self._buffer.pop(timeframe, [])
        if not results:
            return True

        # Group by direction bucket for readability
        vetoed   = [r for r in results if r.veto_killed]
        no_signal = [r for r in results if not r.veto_killed]

        lines = [f"\u27a1️ **No-Trend Summary** [{timeframe}] — {len(results)} tickers"]

        if no_signal:
            lines.append(f"\n**🟣 Below threshold ({len(no_signal)})**")
            for r in no_signal:
                sig_icons = " ".join(
                    f"{'\u2713' if s.passed else '\u2717'}{s.name[:3]}"
                    for s in r.signals if not getattr(s, "is_veto", False)
                )
                lines.append(f"`{r.ticker:<10}` {r.score}/5  {sig_icons}")

        if vetoed:
            lines.append(f"\n**🛑 Vetoed ({len(vetoed)})**")
            for r in vetoed:
                failed = ", ".join(
                    s.name for s in r.signals
                    if getattr(s, "is_veto", False) and not s.passed
                )
                lines.append(f"`{r.ticker:<10}` would-be {r.initial_direction.upper()} — vetoed by {failed}")


        message = "\n".join(lines)
        # Discord has a 2000-char limit — truncate gracefully
        if len(message) > 1990:
            message = message[:1990] + "\n*...truncated*"

        # Attach a chart if any result has one (prefer trending-but-vetoed results)
        chart_path = None
        for r in (vetoed + no_signal):
            cp = r.chart_path or r.chart_1h_path or r.chart_1d_path
            if cp:
                chart_path = cp
                break

        logger.info(f"  📤 Flushing no-trend batch [{timeframe}]: {len(results)} tickers")
        return self._post(
            message=message,
            chart_path=chart_path,
            timeframe=timeframe,
            label="NO-TREND",
        )

    def send_message(self, text: str, timeframe: str = None) -> bool:
        return self._post(message=text, chart_path=None, timeframe=timeframe, label="NO-TREND-MSG")



# ─────────────────────────────────────────────────────────────────────────────
# ALERT DISPATCHER
# ─────────────────────────────────────────────────────────────────────────────

class AlertDispatcher:
    """Manages dispatching alerts to all configured platforms."""

    def __init__(self):
        self._trend_platforms: List[BasePlatform] = []    # fires for confirmed trends
        self._veto_platforms: List[BasePlatform] = []     # fires for vetoed signals
        self._notrend_platforms: List[BasePlatform] = []  # fires for no-trend results
        self._initialized = False
        self._last_alerted: Dict[Tuple[str, str, str], float] = {}

    def _initialize_platforms(self):
        if self._initialized:
            return

        notif = CFG.notifications

        # Telegram — trends only
        if notif.telegram.enabled and notif.telegram.bot_token:
            self._trend_platforms.append(TelegramPlatform(
                token=notif.telegram.bot_token,
                chat_id=notif.telegram.chat_id,
            ))

        # Discord trends channel
        if notif.discord.enabled and notif.discord.webhook_url:
            self._trend_platforms.append(DiscordPlatform(
                webhook_url=notif.discord.webhook_url,
            ))

        # Discord vetos channel
        if notif.discord_vetos.enabled and notif.discord_vetos.webhook_url:
            self._veto_platforms.append(DiscordVetosPlatform(
                webhook_url=notif.discord_vetos.webhook_url,
            ))

        # Discord no-trend channel
        if notif.discord_no_trend.enabled and notif.discord_no_trend.webhook_url:
            self._notrend_platforms.append(DiscordNoTrendPlatform(
                webhook_url=notif.discord_no_trend.webhook_url,
            ))

        self._initialized = True

    def dispatch(self, result: TrendResult):
        """Dispatch a trend result to the correct platform set based on outcome."""
        self._initialize_platforms()

        is_confirmed_trend = result.is_trending and not result.veto_killed
        is_vetoed          = result.veto_killed and result.initial_direction != "none"
        is_no_trend        = not result.is_trending and not result.veto_killed

        if is_confirmed_trend:
            for platform in self._trend_platforms:
                platform.send_alert(result)
            key = (result.ticker, result.timeframe, result.direction)
            self._last_alerted[key] = time.monotonic()

        elif is_vetoed:
            for platform in self._veto_platforms:
                platform.send_alert(result)

        elif is_no_trend:
            # No-trend platform buffers internally; flush via flush_no_trend_batch()
            for platform in self._notrend_platforms:
                platform.send_alert(result)

    def flush_no_trend_batch(self, timeframe: str) -> None:
        """
        Flush buffered no-trend results for `timeframe` as one consolidated message.
        Call this AFTER run_parallel_scan() finishes for the timeframe.
        """
        self._initialize_platforms()
        for platform in self._notrend_platforms:
            if hasattr(platform, "flush_batch"):
                platform.flush_batch(timeframe)

    def dispatch_message(self, text: str, timeframe: str = None):
        """Dispatch a plain text message to trend + veto platforms (scan start/end notices)."""
        self._initialize_platforms()
        for platform in self._trend_platforms:
            platform.send_message(text, timeframe)
        for platform in self._veto_platforms:
            platform.send_message(text, timeframe)


    def clear_discord_messages(self, timeframe: str = None):
        """Delete all previously sent Discord messages to clean up the channel."""
        import os
        msg_ids_file = "trend_scanner/output/discord_msg_ids.txt"
        if not os.path.exists(msg_ids_file):
            return

        try:
            with open(msg_ids_file, "r") as f:
                lines = f.readlines()

            if not lines:
                return

            logger.info(f"  🧹 Cleaning up previous Discord messages (timeframe={timeframe})...")

            kept_lines = []
            for line in lines:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                webhook_url = parts[0]
                msg_id = parts[1]
                msg_tf = parts[2] if len(parts) > 2 else None

                if timeframe and msg_tf and msg_tf != timeframe:
                    kept_lines.append(line + "\n")
                    continue

                try:
                    time.sleep(0.5)   # respect Discord rate limits
                    requests.delete(f"{webhook_url}/messages/{msg_id}", timeout=10)
                except Exception:
                    kept_lines.append(line + "\n")

            with open(msg_ids_file, "w") as f:
                f.writelines(kept_lines)

            logger.info("  ✨ Discord channels cleaned.")
        except Exception as e:
            logger.error(f"  ❌ Failed to clean Discord messages: {e}")


# Global singleton dispatcher
DISPATCHER = AlertDispatcher()


def dispatch_trend_alert(result: TrendResult):
    """Route a TrendResult to the appropriate Discord/Telegram channels."""
    DISPATCHER.dispatch(result)


def dispatch_text_message(text: str, timeframe: str = None):
    """Send a plain text message (e.g. scan start) to all active platforms."""
    DISPATCHER.dispatch_message(text, timeframe)
