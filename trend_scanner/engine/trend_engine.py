"""
trend_engine.py — Aggregates all 5 signals into a final TrendResult.

Usage:
    engine = TrendEngine()
    result = engine.analyze(df, ticker="AAPL", timeframe="1h")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import pandas as pd

from trend_scanner.config import CFG
from trend_scanner.engine.signals import (
    SignalResult,
    signal_linreg_slope,
    signal_mann_kendall,
    signal_adx,
    signal_market_structure,
    signal_pivot_channel,
)


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrendResult:
    ticker:           str
    timeframe:        str
    direction:        str          # 'up' | 'down' | 'none'
    score:            int          # 0–5 (signals passed)
    confidence:       float        # 0.0–1.0 (mean signal score of passing signals)
    signals:          List[SignalResult] = field(default_factory=list)
    signals_passed:   List[str] = field(default_factory=list)
    candles_analyzed: int = 0
    vlm_verdict:      Optional[str] = None
    vlm_confidence:   Optional[float] = None
    chart_1h_path:    Optional[str] = None
    chart_1d_path:    Optional[str] = None

    @property
    def is_trending(self) -> bool:
        return self.direction in ("up", "down")

    @property
    def emoji(self) -> str:
        if self.direction == "up":
            return "🚀"
        elif self.direction == "down":
            return "🔻"
        return "➡️"

    @property
    def direction_label(self) -> str:
        return {
            "up":   "UPTREND",
            "down": "DOWNTREND",
            "none": "NO TREND",
        }.get(self.direction, "UNKNOWN")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker":           self.ticker,
            "timeframe":        self.timeframe,
            "direction":        self.direction,
            "score":            self.score,
            "confidence":       round(self.confidence, 3),
            "signals_passed":   ", ".join(self.signals_passed),
            "candles_analyzed": self.candles_analyzed,
            "vlm_verdict":      self.vlm_verdict or "",
            "vlm_confidence":   self.vlm_confidence or "",
            "chart_path":       self.chart_1h_path or self.chart_1d_path or "",
            # Individual signal details
            **{
                f"sig_{s.name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')}": (
                    f"{'✓' if s.passed else '✗'} {s.direction} {s.score:.2f}"
                )
                for s in self.signals
            },
        }

    def summary_line(self) -> str:
        bar = "█" * self.score + "░" * (5 - self.score)
        return (
            f"{self.emoji} [{bar}] {self.score}/5  "
            f"{self.ticker:<12} {self.timeframe:<4}  "
            f"{self.direction_label:<10}  "
            f"conf={self.confidence:.0%}  "
            f"candles={self.candles_analyzed}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TrendEngine:
    """
    Runs all 5 signals and aggregates results into a TrendResult.

    Only the last `analysis_window` candles are used (configurable).
    """

    def __init__(self, config=None):
        self.cfg = config or CFG.trend

    def analyze(
        self,
        df: pd.DataFrame,
        ticker: str,
        timeframe: str,
    ) -> TrendResult:
        """
        Run the full 5-signal trend analysis.

        Parameters
        ----------
        df        : Full OHLCV DataFrame (any length)
        ticker    : Ticker symbol
        timeframe : Timeframe string

        Returns
        -------
        TrendResult with full signal breakdown
        """
        if df is None or len(df) < 50:
            return TrendResult(
                ticker=ticker, timeframe=timeframe, direction="none",
                score=0, confidence=0.0, candles_analyzed=0,
            )

        # Slice to analysis window
        window = min(self.cfg.analysis_window, len(df))
        analysis_df = df.iloc[-window:].reset_index(drop=True)

        # Run all 5 signals
        all_signals: List[SignalResult] = [
            signal_linreg_slope(analysis_df),
            signal_mann_kendall(analysis_df),
            signal_adx(analysis_df),
            signal_market_structure(analysis_df),
            signal_pivot_channel(analysis_df),
        ]

        # Determine overall direction by majority vote among PASSING signals
        up_votes   = sum(1 for s in all_signals if s.passed and s.direction == "up")
        down_votes = sum(1 for s in all_signals if s.passed and s.direction == "down")
        total_pass = sum(1 for s in all_signals if s.passed)

        if up_votes > down_votes and up_votes >= self.cfg.min_signals_for_trend:
            direction = "up"
        elif down_votes > up_votes and down_votes >= self.cfg.min_signals_for_trend:
            direction = "down"
        else:
            direction = "none"

        # Score = number of signals that agree with final direction
        if direction != "none":
            score = sum(
                1 for s in all_signals
                if s.passed and s.direction == direction
            )
        else:
            score = 0

        # Confidence = mean score of passing signals
        passing = [s for s in all_signals if s.passed and s.direction == direction]
        confidence = float(sum(s.score for s in passing) / len(passing)) if passing else 0.0

        signals_passed = [s.name for s in passing]

        return TrendResult(
            ticker=ticker,
            timeframe=timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            signals=all_signals,
            signals_passed=signals_passed,
            candles_analyzed=window,
        )
