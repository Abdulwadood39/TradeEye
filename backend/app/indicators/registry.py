from __future__ import annotations

from typing import Dict

from backend.app.indicators.base import BaseIndicator
from backend.app.indicators.continuous_trend import ContinuousTrendIndicator

_registry: Dict[str, BaseIndicator] = {}


def register(indicator: BaseIndicator) -> None:
    _registry[indicator.slug] = indicator


def get(slug: str) -> BaseIndicator:
    if slug not in _registry:
        raise KeyError(f"Indicator '{slug}' not registered")
    return _registry[slug]


def list_slugs() -> list[str]:
    return list(_registry.keys())


def init_registry() -> None:
    if not _registry:
        register(ContinuousTrendIndicator())
