from __future__ import annotations

import pandas as pd

from backend.app.indicators.base import BaseIndicator, IndicatorResult
from trend_scanner.config import CFG
from trend_scanner.engine.trend_engine import TrendEngine


class ContinuousTrendIndicator(BaseIndicator):
    slug = "continuous_trend"

    def analyze(
        self,
        df: pd.DataFrame,
        *,
        ticker: str,
        timeframe: str,
        bars: int,
        config: dict | None = None,
    ) -> IndicatorResult:
        if df is None or len(df) < 50:
            return IndicatorResult(direction="NONE", bars_scanned=bars)

        analysis_df = df.iloc[-bars:].reset_index(drop=True)
        engine = TrendEngine(config=CFG.trend, vetoes_config=CFG.vetoes)
        result = engine.analyze(analysis_df, ticker=ticker, timeframe=timeframe)

        direction = result.direction.upper() if result.direction != "none" else "NONE"
        return IndicatorResult(
            direction=direction,
            score=result.score,
            confidence=result.confidence,
            bars_scanned=result.candles_analyzed or bars,
            metadata={
                "veto_killed": result.veto_killed,
                "initial_direction": result.initial_direction,
                "signals_passed": result.signals_passed,
            },
            raw_result=result,
        )
