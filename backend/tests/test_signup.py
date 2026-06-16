import pytest
from pydantic import ValidationError

from backend.app.schemas.auth import SignupRequest
from backend.app.schemas.enums import PrimaryMarket, TradingStyle


def test_signup_request_valid():
    req = SignupRequest(
        full_name="Samar Ahmed",
        email="test@example.com",
        password="password123",
        confirm_password="password123",
        trading_style=TradingStyle.SWING_TRADER,
        primary_market=PrimaryMarket.FOREX,
    )
    assert req.full_name == "Samar Ahmed"
    assert req.trading_style == TradingStyle.SWING_TRADER


def test_signup_password_mismatch():
    with pytest.raises(ValidationError, match="Passwords do not match"):
        SignupRequest(
            full_name="Test User",
            email="test@example.com",
            password="password123",
            confirm_password="different",
            trading_style=TradingStyle.DAY_TRADER,
            primary_market=PrimaryMarket.STOCKS,
        )


def test_signup_strips_full_name():
    req = SignupRequest(
        full_name="  Jane Doe  ",
        email="jane@example.com",
        password="password123",
        confirm_password="password123",
        trading_style=TradingStyle.SCALPER,
        primary_market=PrimaryMarket.CRYPTOCURRENCY,
    )
    assert req.full_name == "Jane Doe"
