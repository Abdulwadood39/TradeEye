"""Trial period and subscription add-ons

Revision ID: 20260707_trial_addons
Revises: 20260629_whop_billing
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260707_trial_addons"
down_revision = "20260629_whop_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("plan_kind", sa.String(length=16), nullable=False, server_default="subscription"),
    )
    op.add_column(
        "plans",
        sa.Column("addon_bonus_subscriptions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("bonus_subscriptions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "user_plan_addons",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("subscription_id", sa.CHAR(length=36), nullable=False),
        sa.Column("plan_id", sa.CHAR(length=36), nullable=False),
        sa.Column("provider_membership_id", sa.String(length=128), nullable=False),
        sa.Column("bonus_subscriptions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_membership_id"),
    )
    op.execute("UPDATE plans SET plan_kind = 'internal' WHERE slug IN ('free', 'admin')")


def downgrade() -> None:
    op.drop_table("user_plan_addons")
    op.drop_column("subscriptions", "bonus_subscriptions")
    op.drop_column("plans", "addon_bonus_subscriptions")
    op.drop_column("plans", "plan_kind")
