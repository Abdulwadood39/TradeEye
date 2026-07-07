from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.db.models.billing import Plan, Subscription, UserPlanAddon
from backend.app.db.models.scan import NotificationMessage
from backend.app.db.models.user import (
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserNotificationSettings,
    UserSubscription,
)
from backend.app.services.billing_constants import (
    ACTIVE_BILLING_STATUSES,
    BILLING_PROVIDER,
    PLAN_KIND_SUBSCRIPTION,
)


class UserDeletionError(Exception):
    pass


@dataclass(frozen=True)
class AdminUserStats:
    registered_users: int
    paid_users: int
    addons_sold: int


@dataclass(frozen=True)
class AdminUserRow:
    id: UUID
    email: str
    full_name: str
    created_at: object
    plan_name: str
    plan_slug: str
    is_paid: bool
    email_verified: bool


async def get_admin_user_stats(db: AsyncSession) -> AdminUserStats:
    registered = int((await db.execute(select(func.count()).select_from(User))).scalar() or 0)

    paid = int(
        (
            await db.execute(
                select(func.count(func.distinct(Subscription.user_id)))
                .join(Plan, Subscription.plan_id == Plan.id)
                .where(
                    Plan.plan_kind == PLAN_KIND_SUBSCRIPTION,
                    Plan.whop_plan_id.isnot(None),
                    Subscription.provider == BILLING_PROVIDER,
                    Subscription.status.in_(tuple(ACTIVE_BILLING_STATUSES)),
                )
            )
        ).scalar()
        or 0
    )

    addons_sold = int((await db.execute(select(func.count()).select_from(UserPlanAddon))).scalar() or 0)

    return AdminUserStats(
        registered_users=registered,
        paid_users=paid,
        addons_sold=addons_sold,
    )


async def list_admin_users(db: AsyncSession) -> list[AdminUserRow]:
    rows = (
        await db.execute(
            select(User, Plan, Subscription)
            .outerjoin(Subscription, Subscription.user_id == User.id)
            .outerjoin(Plan, Plan.id == Subscription.plan_id)
            .order_by(User.created_at.desc())
        )
    ).all()

    users: list[AdminUserRow] = []
    for user, plan, billing_sub in rows:
        is_paid = bool(
            plan is not None
            and billing_sub is not None
            and plan.plan_kind == PLAN_KIND_SUBSCRIPTION
            and plan.whop_plan_id
            and billing_sub.provider == BILLING_PROVIDER
            and billing_sub.status in ACTIVE_BILLING_STATUSES
        )
        users.append(
            AdminUserRow(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                created_at=user.created_at,
                plan_name=plan.name if plan is not None else "—",
                plan_slug=plan.slug if plan is not None else "—",
                is_paid=is_paid,
                email_verified=user.email_verified_at is not None,
            )
        )
    return users


def _assert_user_may_be_deleted(user: User) -> None:
    settings = get_settings()
    if user.email.lower() == settings.admin_test_user_email.lower():
        raise UserDeletionError("The admin test account cannot be deleted")


async def delete_user_account(db: AsyncSession, user_id: UUID) -> None:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise UserDeletionError("User not found")

    _assert_user_may_be_deleted(user)

    billing_sub = (
        await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    ).scalar_one_or_none()
    if billing_sub is not None:
        await db.execute(delete(UserPlanAddon).where(UserPlanAddon.subscription_id == billing_sub.id))
        await db.execute(delete(Subscription).where(Subscription.user_id == user_id))

    await db.execute(delete(NotificationMessage).where(NotificationMessage.user_id == user_id))
    await db.execute(delete(UserSubscription).where(UserSubscription.user_id == user_id))
    await db.execute(delete(UserNotificationSettings).where(UserNotificationSettings.user_id == user_id))
    await db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user_id))
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()
