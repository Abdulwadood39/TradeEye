from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field


class IndicatorResult(BaseModel):
    direction: Literal["UP", "DOWN", "NONE"]
    score: int = 0
    confidence: float = 0.0
    bars_scanned: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_result: Any = None


class BaseIndicator(ABC):
    slug: str

    @abstractmethod
    def analyze(
        self,
        df: pd.DataFrame,
        *,
        ticker: str,
        timeframe: str,
        bars: int,
        config: dict | None = None,
    ) -> IndicatorResult:
        pass
