"""
dispatcher.py — Modular alert dispatcher for external communication platforms.
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
        """Send an alert to the platform. Returns True if successful."""
        pass

    @abstractmethod
    def send_message(self, text: str) -> bool:
        """Send a plain text message to the platform. Returns True if successful."""
        pass


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
        
        success = True
        chart_path = getattr(result, "chart_1h_path", None) or getattr(result, "chart_1d_path", None)
        
        for cid in self.chat_ids:
            try:
                # If chart exists, send photo with caption
                if chart_path:
                    # We need to reopen the file for each request if we are iterating
                    with open(chart_path, 'rb') as photo:
                        resp = requests.post(
                            url + "sendPhoto",
                            data={"chat_id": cid, "caption": message, "parse_mode": "Markdown"},
                            files={"photo": photo},
                            timeout=30
                        )
                else:
                    resp = requests.post(
                        url + "sendMessage",
                        data={"chat_id": cid, "text": message, "parse_mode": "Markdown"},
                        timeout=30
                    )
                
                resp.raise_for_status()
                logger.info(f"  📩 Telegram alert sent for {result.ticker} [{result.timeframe}] to {cid}")
            except Exception as e:
                logger.error(f"  ❌ Failed to send Telegram alert to {cid}: {e}")
                success = False
                
        return success

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_ids:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        success = True
        
        for cid in self.chat_ids:
            try:
                resp = requests.post(
                    url,
                    data={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                    timeout=30
                )
                resp.raise_for_status()
                logger.info(f"  📩 Telegram message sent to {cid}")
            except Exception as e:
                logger.error(f"  ❌ Failed to send Telegram message to {cid}: {e}")
                success = False
                
        return success


class DiscordPlatform(BasePlatform):
    """Sends trend alerts to a Discord webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_alert(self, result: TrendResult) -> bool:
        if not self.webhook_url:
            logger.warning("  ⚠️  Discord webhook_url missing. Cannot send alert.")
            return False

        message = (
            f"**{result.emoji} {result.direction_label} Alert: {result.ticker}**\n"
            f"• Timeframe: {result.timeframe}\n"
            f"• Score: {result.score}/5\n"
            f"• Confidence: {result.confidence:.0%}\n"
        )
        
        if result.vlm_verdict:
            message += f"• VLM: {result.vlm_verdict}\n"

        success = True
        chart_path = getattr(result, "chart_1h_path", None) or getattr(result, "chart_1d_path", None)
        
        try:
            if chart_path:
                with open(chart_path, 'rb') as photo:
                    resp = requests.post(
                        self.webhook_url,
                        data={"content": message},
                        files={"file": photo},
                        timeout=30
                    )
            else:
                resp = requests.post(
                    self.webhook_url,
                    json={"content": message},
                    timeout=30
                )
            
            resp.raise_for_status()
            logger.info(f"  📩 Discord alert sent for {result.ticker} [{result.timeframe}]")
        except Exception as e:
            logger.error(f"  ❌ Failed to send Discord alert: {e}")
            success = False
            
        return success

    def send_message(self, text: str) -> bool:
        if not self.webhook_url:
            return False

        try:
            resp = requests.post(
                self.webhook_url,
                json={"content": text},
                timeout=30
            )
            resp.raise_for_status()
            logger.info("  📩 Discord message sent")
            return True
        except Exception as e:
            logger.error(f"  ❌ Failed to send Discord message: {e}")
            return False


class AlertDispatcher:
    """Manages dispatching alerts to all configured platforms."""

    # Minimum seconds between repeat alerts for the same (ticker, timeframe, direction).
    # Prevents flooding when the scanner re-fires every minute on an ongoing trend.

    def __init__(self):
        self._platforms: List[BasePlatform] = []
        self._initialized = False
        # key: (ticker, timeframe, direction) → last alert epoch timestamp
        self._last_alerted: Dict[Tuple[str, str, str], float] = {}

    def _initialize_platforms(self):
        if self._initialized:
            return

        if getattr(CFG, "notifications", None):
            # Register Telegram if enabled
            if CFG.notifications.telegram.enabled:
                self._platforms.append(TelegramPlatform(
                    token=CFG.notifications.telegram.bot_token,
                    chat_id=CFG.notifications.telegram.chat_id,
                ))
            # Register Discord if enabled
            if CFG.notifications.discord.enabled:
                self._platforms.append(DiscordPlatform(
                    webhook_url=CFG.notifications.discord.webhook_url,
                ))

        self._initialized = True

    

    def dispatch(self, result: TrendResult):
        """Dispatch a trend result to all registered communication platforms."""
        if not result.is_trending or getattr(result, "veto_killed", False):
            return

        self._initialize_platforms()

        key = (result.ticker, result.timeframe, result.direction)

        for platform in self._platforms:
            platform.send_alert(result)

        self._last_alerted[key] = time.monotonic()

    def dispatch_message(self, text: str):
        """Dispatch a plain text message to all registered communication platforms."""
        self._initialize_platforms()
        for platform in self._platforms:
            platform.send_message(text)


# Global singleton dispatcher
DISPATCHER = AlertDispatcher()

def dispatch_trend_alert(result: TrendResult):
    """Helper function to dispatch an alert using the global dispatcher."""
    DISPATCHER.dispatch(result)

def dispatch_text_message(text: str):
    """Helper function to dispatch a plain text message using the global dispatcher."""
    DISPATCHER.dispatch_message(text)
