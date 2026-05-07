"""
trend_engine.py — Aggregates signals + hard veto gates into a final TrendResult.

Decision logic:
  1. Run 5 core signals → direction by majority vote
  2. Run R² Linearity veto (V1)
  3. Run ATR Consolidation veto (V2)
  4. Run Trend Break veto (V3) — uses direction from step 1
  5. If ANY veto fails → direction = "none"
  6. Score = number of core signals agreeing with direction
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
    veto_atr_consolidation,
    veto_trend_break,
)


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrendResult:
    ticker:           str
    timeframe:        str
    direction:        str          # 'up' | 'down' | 'none'
    score:            int          # 0–5 (core signals passed)
    confidence:       float        # 0.0–1.0
    signals:          List[SignalResult] = field(default_factory=list)
    vetoes:           List[SignalResult] = field(default_factory=list)
    signals_passed:   List[str] = field(default_factory=list)
    vetoes_failed:    List[str] = field(default_factory=list)
    candles_analyzed: int = 0
    veto_killed:      bool = False   # True if a veto overrode a core trend signal
    vlm_verdict:      Optional[str] = None
    vlm_confidence:   Optional[float] = None
    chart_1h_path:    Optional[str] = None
    chart_1m_path:    Optional[str] = None

    @property
    def is_trending(self) -> bool:
        return self.direction in ("up", "down")

    @property
    def emoji(self) -> str:
        if self.direction == "up":   return "🚀"
        if self.direction == "down": return "🔻"
        return "➡️"

    @property
    def direction_label(self) -> str:
        if self.direction == "up":   return "UPTREND"
        if self.direction == "down": return "DOWNTREND"
        return "SIDEWAYS" if self.veto_killed else "NO TREND"

    def to_dict(self) -> Dict[str, Any]:
        row = {
            "ticker":           self.ticker,
            "timeframe":        self.timeframe,
            "direction":        self.direction,
            "score":            self.score,
            "confidence":       round(self.confidence, 3),
            "veto_killed":      self.veto_killed,
            "vetoes_failed":    ", ".join(self.vetoes_failed),
            "signals_passed":   ", ".join(self.signals_passed),
            "candles_analyzed": self.candles_analyzed,
            "vlm_verdict":      self.vlm_verdict or "",
            "vlm_confidence":   self.vlm_confidence or "",
            "chart_path":       self.chart_1h_path or self.chart_1m_path or "",
        }
        for s in self.signals + self.vetoes:
            key = f"sig_{s.name.lower().replace(' ', '_').replace('²','2').replace('(','').replace(')','')}"
            row[key] = f"{'✓' if s.passed else '✗'} {s.direction} {s.score:.2f}"
        return row

    def summary_line(self) -> str:
        bar   = "█" * self.score + "░" * (5 - self.score)
        veto  = f"  [VETO: {', '.join(self.vetoes_failed)}]" if self.veto_killed else ""
        return (
            f"{self.emoji} [{bar}] {self.score}/5  "
            f"{self.ticker:<12} {self.timeframe:<4}  "
            f"{self.direction_label:<10}  "
            f"conf={self.confidence:.0%}  "
            f"candles={self.candles_analyzed}"
            f"{veto}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TrendEngine:
    def __init__(self, config=None):
        self.cfg = config or CFG.trend

    def _analysis_window(self, timeframe: str, available: int) -> int:
        """Return appropriate window size for the timeframe."""
        tf = timeframe.lower()
        if tf == "1m":
            w = self.cfg.analysis_window_1m
        elif tf in ("1h", "2h", "4h"):
            w = self.cfg.analysis_window_1h
        else:
            w = self.cfg.analysis_window
        return min(w, available)

    def analyze(self, df: pd.DataFrame, ticker: str, timeframe: str) -> TrendResult:
        if df is None or len(df) < 50:
            return TrendResult(
                ticker=ticker, timeframe=timeframe, direction="none",
                score=0, confidence=0.0, candles_analyzed=0,
            )

        window      = self._analysis_window(timeframe, len(df))
        analysis_df = df.iloc[-window:].reset_index(drop=True)

        # ── Step 1: Run 5 core signals ────────────────────────────────────────
        core_signals: List[SignalResult] = [
            signal_linreg_slope(analysis_df),
            signal_mann_kendall(analysis_df),
            signal_adx(analysis_df),
            signal_market_structure(analysis_df),
            signal_pivot_channel(analysis_df),
        ]

        # ── Step 2: Majority vote on direction ────────────────────────────────
        up_votes   = sum(1 for s in core_signals if s.passed and s.direction == "up")
        down_votes = sum(1 for s in core_signals if s.passed and s.direction == "down")

        if up_votes > down_votes and up_votes >= self.cfg.min_signals_for_trend:
            raw_direction = "up"
        elif down_votes > up_votes and down_votes >= self.cfg.min_signals_for_trend:
            raw_direction = "down"
        else:
            raw_direction = "none"

        # ── Step 3: Hard veto signals ─────────────────────────────────────────
        veto_r2  = veto_r2_linearity(analysis_df)
        veto_atr = veto_atr_consolidation(analysis_df)
        veto_brk = veto_trend_break(analysis_df, raw_direction)

        veto_signals = [veto_r2, veto_atr, veto_brk]
        failed_vetos = [v.name for v in veto_signals if not v.passed]
        veto_killed  = len(failed_vetos) > 0 and raw_direction != "none"

        # Final direction: only survives if all vetoes pass
        direction = raw_direction if not veto_killed else "none"

        # ── Step 4: Score + confidence ────────────────────────────────────────
        if direction != "none":
            score    = sum(1 for s in core_signals if s.passed and s.direction == direction)
            passing  = [s for s in core_signals if s.passed and s.direction == direction]
            confidence = float(sum(s.score for s in passing) / len(passing)) if passing else 0.0
            signals_passed = [s.name for s in passing]
        else:
            score = 0; confidence = 0.0; signals_passed = []

        return TrendResult(
            ticker=ticker,
            timeframe=timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            signals=core_signals,
            vetoes=veto_signals,
            signals_passed=signals_passed,
            vetoes_failed=failed_vetos,
            candles_analyzed=window,
            veto_killed=veto_killed,
        )
