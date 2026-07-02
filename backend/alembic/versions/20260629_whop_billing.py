"""Add Whop billing columns

Revision ID: 20260629_whop_billing
Revises:
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260629_whop_billing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("whop_plan_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_plans_whop_plan_id", "plans", ["whop_plan_id"])
    op.add_column("billing_events", sa.Column("external_event_id", sa.String(length=128), nullable=True))
    op.create_index("ix_billing_events_external_event_id", "billing_events", ["external_event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_billing_events_external_event_id", table_name="billing_events")
    op.drop_column("billing_events", "external_event_id")
    op.drop_constraint("uq_plans_whop_plan_id", "plans", type_="unique")
    op.drop_column("plans", "whop_plan_id")
