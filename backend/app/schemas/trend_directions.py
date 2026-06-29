from __future__ import annotations

PUBLIC_TREND_DIRECTIONS = ("UP", "DOWN")
VETOED_TREND_DIRECTIONS = ("Vetoed_UP", "Vetoed_DOWN")
STORABLE_TREND_DIRECTIONS = PUBLIC_TREND_DIRECTIONS + VETOED_TREND_DIRECTIONS
NOTIFIABLE_TREND_DIRECTIONS = PUBLIC_TREND_DIRECTIONS


def is_vetoed_direction(direction: str) -> bool:
    return direction in VETOED_TREND_DIRECTIONS


def visible_directions_for_user(*, is_admin_test_user: bool) -> tuple[str, ...]:
    if is_admin_test_user:
        return STORABLE_TREND_DIRECTIONS
    return PUBLIC_TREND_DIRECTIONS
