"""
dispatcher.py — Modular alert dispatcher for external communication platforms.
"""
from __future__ import annotations

import logging
import requests
from abc import ABC, abstractmethod
from typing import List

from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendResult

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    """Base interface for all notification platforms."""
    
    @abstractmethod
    def send_alert(self, result: TrendResult) -> bool:
        """Send an alert to the platform. Returns True if successful."""
        pass


class TelegramPlatform(BasePlatform):
    """Sends trend alerts to a Telegram chat."""
    
    def __init__(self, token: str, chat_id: str):
        
        print(f"telegram Token: {token} Chat ID: {chat_id}")
        self.token = token
        self.chat_id = chat_id

    def send_alert(self, result: TrendResult) -> bool:
        if not self.token or not self.chat_id:
            print("  ⚠️  Telegram token or chat_id missing. Cannot send alert.")
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
        
        try:
            # If chart exists, send photo with caption
            chart_path = getattr(result, "chart_1h_path", None) or getattr(result, "chart_1d_path", None)
            if chart_path:
                with open(chart_path, 'rb') as photo:
                    resp = requests.post(
                        url + "sendPhoto",
                        data={"chat_id": self.chat_id, "caption": message, "parse_mode": "Markdown"},
                        files={"photo": photo},
                        timeout=30
                    )
            else:
                resp = requests.post(
                    url + "sendMessage",
                    data={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                    timeout=30
                )
            
            resp.raise_for_status()
            print(f"  📩 Telegram alert sent for {result.ticker} [{result.timeframe}]")
            return True
        except Exception as e:
            print(f"  ❌ Failed to send Telegram alert: {e}")
            return False


class AlertDispatcher:
    """Manages dispatching alerts to all configured platforms."""
    
    def __init__(self):
        self._platforms: List[BasePlatform] = []
        self._initialized = False
        
    def _initialize_platforms(self):
        if self._initialized:
            return
            
        if getattr(CFG, "notifications", None):
            # Register Telegram if enabled
            if CFG.notifications.telegram.enabled:
                self._platforms.append(TelegramPlatform(
                    token=CFG.notifications.telegram.bot_token,
                    chat_id=CFG.notifications.telegram.chat_id
                ))
            
        self._initialized = True

    def dispatch(self, result: TrendResult):
        """Dispatch a trend result to all registered communication platforms."""
        # Only dispatch if it's a valid trend and not vetoed
        if not result.is_trending or getattr(result, "veto_killed", False):
            return
            
        self._initialize_platforms()
        for platform in self._platforms:
            platform.send_alert(result)


# Global singleton dispatcher
DISPATCHER = AlertDispatcher()

def dispatch_trend_alert(result: TrendResult):
    """Helper function to dispatch an alert using the global dispatcher."""
    DISPATCHER.dispatch(result)
