"""
trend_engine.py — Aggregates all 5 signals into a final TrendResult.

Usage:
    engine = TrendEngine()
    result = engine.analyze(df, ticker="AAPL", timeframe="1h")

Veto gates are controlled by CFG.vetoes.enabled (scanner.toml [vetoes] enabled).
Analysis window per timeframe is driven by CFG.trend.analysis_windows dict.
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
    veto_r2_linearity,
    veto_rolling_r2,
    veto_atr_consolidation,
    veto_kaufman_er,
    veto_trend_break,
    veto_ema_alignment,
    veto_sideways_body,
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
    chart_path:       Optional[str] = None    # unified chart path (any timeframe)
    chart_1h_path:    Optional[str] = None    # kept for backward compat
    chart_1d_path:    Optional[str] = None    # kept for backward compat
    veto_killed:      bool = False
    initial_direction: str = "none"           # direction before veto filtering

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
            "initial_direction": self.initial_direction,
            "score":            self.score,
            "confidence":       round(self.confidence, 3),
            "signals_passed":   ", ".join(self.signals_passed),
            "candles_analyzed": self.candles_analyzed,
            "veto_killed":      self.veto_killed,
            "vlm_verdict":      self.vlm_verdict or "",
            "vlm_confidence":   self.vlm_confidence or "",
            "chart_path":       self.chart_path or self.chart_1h_path or self.chart_1d_path or "",
            # Individual signal details
            **{
                f"sig_{s.name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace('²', '2')}": (
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

    Veto gates run only when CFG.vetoes.enabled is True.
    Analysis window is resolved from CFG.trend.analysis_windows per timeframe.
    """

    def __init__(self, config=None, vetoes_config=None):
        self.cfg = config or CFG.trend
        self.vetoes_cfg = vetoes_config if vetoes_config is not None else CFG.vetoes

    def analyze(
        self,
        df: pd.DataFrame,
        ticker: str,
        timeframe: str,
    ) -> TrendResult:
        """
        Run the full 5-signal trend analysis, then apply veto gates.

        Parameters
        ----------
        df        : Full OHLCV DataFrame (any length)
        ticker    : Ticker symbol
        timeframe : Timeframe string (e.g. '1h', '5m', '30m')

        Returns
        -------
        TrendResult with full signal breakdown
        """
        if df is None or len(df) < 50:
            return TrendResult(
                ticker=ticker, timeframe=timeframe, direction="none",
                score=0, confidence=0.0, candles_analyzed=0,
                initial_direction="none",
            )

        # Slice to analysis window — driven by CFG for any timeframe
        window = min(self.cfg.window_for(timeframe), len(df))
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

        if up_votes > down_votes and up_votes >= self.cfg.min_signals_for_trend:
            initial_direction = "up"
        elif down_votes > up_votes and down_votes >= self.cfg.min_signals_for_trend:
            initial_direction = "down"
        else:
            initial_direction = "none"

        direction = initial_direction
        veto_killed = False

        if direction != "none" and self.vetoes_cfg.enabled:
            # Run Veto Gates (order: cheapest/fastest first)
            vetoes: List[SignalResult] = [
                veto_r2_linearity(analysis_df),
                veto_rolling_r2(analysis_df),
                veto_atr_consolidation(analysis_df),
                veto_kaufman_er(analysis_df),
                veto_sideways_body(analysis_df),
                veto_ema_alignment(analysis_df, direction),
                veto_trend_break(analysis_df, direction),
            ]
            all_signals.extend(vetoes)

            for veto in vetoes:
                if not veto.passed:
                    direction = "none"
                    veto_killed = True
                    break  # one failed veto is enough — stop early

        elif direction != "none" and not self.vetoes_cfg.enabled:
            # Vetoes disabled — still log them for visibility but don't apply
            vetoes: List[SignalResult] = [
                veto_r2_linearity(analysis_df),
                veto_rolling_r2(analysis_df),
                veto_atr_consolidation(analysis_df),
                veto_kaufman_er(analysis_df),
                veto_sideways_body(analysis_df),
                veto_ema_alignment(analysis_df, direction),
                veto_trend_break(analysis_df, direction),
            ]
            all_signals.extend(vetoes)

        # Score = number of signals that agree with initial direction (excluding vetoes)
        if initial_direction != "none":
            score = sum(
                1 for s in all_signals
                if s.passed and s.direction == initial_direction and not getattr(s, "is_veto", False)
            )
        else:
            score = sum(1 for s in all_signals if s.passed and not getattr(s, "is_veto", False))

        # Confidence = mean score of passing signals (excluding vetoes)
        passing = [
            s for s in all_signals
            if s.passed and s.direction == initial_direction and not getattr(s, "is_veto", False)
        ]
        confidence = float(sum(s.score for s in passing) / len(passing)) if passing else 0.0

        signals_passed = [s.name for s in passing]

        return TrendResult(
            ticker=ticker,
            timeframe=timeframe,
            direction=direction,
            initial_direction=initial_direction,
            score=score,
            confidence=confidence,
            signals=all_signals,
            signals_passed=signals_passed,
            candles_analyzed=window,
            veto_killed=veto_killed,
        )
