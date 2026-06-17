from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.core.config import get_settings
from backend.app.core.email import send_password_reset_email, send_verification_email
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token,
    hash_password,
    hash_token,
    parse_uuid,
    verify_password,
)
from backend.app.db.models.billing import Plan, Subscription
from backend.app.db.models.user import EmailVerificationToken, PasswordResetToken, User
from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupOptionsResponse,
    SignupRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from backend.app.schemas.enums import (
    PRIMARY_MARKET_LABELS,
    TRADING_STYLE_LABELS,
    PrimaryMarket,
    TradingStyle,
)
from backend.app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response_for_user(user: User) -> TokenResponse:
    sub = str(user.id)
    return TokenResponse(
        access_token=create_access_token(sub),
        refresh_token=create_refresh_token(sub),
        user=UserResponse.from_user(user),
    )


@router.get("/signup-options", response_model=SignupOptionsResponse)
async def signup_options() -> SignupOptionsResponse:
    return SignupOptionsResponse(
        trading_styles=[
            {"value": style.value, "label": TRADING_STYLE_LABELS[style]} for style in TradingStyle
        ],
        primary_markets=[
            {"value": market.value, "label": PRIMARY_MARKET_LABELS[market]} for market in PrimaryMarket
        ],
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(request: Request, body: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        trading_style=body.trading_style.value,
        primary_market=body.primary_market.value,
    )
    db.add(user)
    await db.flush()

    free_plan = await db.execute(select(Plan).where(Plan.slug == "free"))
    plan = free_plan.scalar_one_or_none()
    if plan:
        db.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))

    raw_token = generate_token()
    settings = get_settings()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_expire_hours),
        )
    )
    await db.commit()
    await db.refresh(user)
    await send_verification_email(user.email, raw_token)
    return _token_response_for_user(user)


async def _verify_email_with_token(token: str, db: AsyncSession) -> User:
    token_hash = hash_token(token)
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record is None or record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user_result = await db.execute(select(User).where(User.id == record.user_id))
    user = user_result.scalar_one()
    user.email_verified_at = datetime.now(timezone.utc)
    record.used_at = datetime.now(timezone.utc)
    await db.commit()
    return user


@router.get("/verify-email", response_model=TokenResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await _verify_email_with_token(token, db)
    await db.refresh(user)
    return _token_response_for_user(user)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email_post(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await _verify_email_with_token(body.token, db)
    await db.refresh(user)
    return _token_response_for_user(user)


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request, body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user and user.email_verified_at is None:
        raw_token = generate_token()
        settings = get_settings()
        db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.email_verification_expire_hours),
            )
        )
        await db.commit()
        await send_verification_email(user.email, raw_token)
    return MessageResponse(message="If the account exists and is unverified, a new email has been sent.")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _token_response_for_user(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        sub = payload["sub"]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    user_id = parse_uuid(sub)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return _token_response_for_user(user)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user:
        raw_token = generate_token()
        settings = get_settings()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.password_reset_expire_hours),
            )
        )
        await db.commit()
        await send_password_reset_email(user.email, raw_token)
    return MessageResponse(message="If the account exists, a password reset email has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    token_hash = hash_token(body.token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record is None or record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user_result = await db.execute(select(User).where(User.id == record.user_id))
    user = user_result.scalar_one()
    user.password_hash = hash_password(body.new_password)
    record.used_at = datetime.now(timezone.utc)
    await db.commit()
    return MessageResponse(message="Password reset successfully.")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_user(user)
