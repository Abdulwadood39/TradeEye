from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from backend.app.schemas.enums import (
    PRIMARY_MARKET_LABELS,
    TRADING_STYLE_LABELS,
    PrimaryMarket,
    TradingStyle,
)


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    trading_style: TradingStyle
    primary_market: PrimaryMarket

    @model_validator(mode="after")
    def passwords_match(self) -> "SignupRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    trading_style: str
    trading_style_label: str
    primary_market: str
    primary_market_label: str
    is_active: bool
    email_verified_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user) -> "UserResponse":
        trading = TradingStyle(user.trading_style)
        market = PrimaryMarket(user.primary_market)
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            trading_style=trading.value,
            trading_style_label=TRADING_STYLE_LABELS[trading],
            primary_market=market.value,
            primary_market_label=PRIMARY_MARKET_LABELS[market],
            is_active=user.is_active,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class EnumOption(BaseModel):
    value: str
    label: str


class SignupOptionsResponse(BaseModel):
    trading_styles: list[EnumOption]
    primary_markets: list[EnumOption]


class MessageResponse(BaseModel):
    message: str
