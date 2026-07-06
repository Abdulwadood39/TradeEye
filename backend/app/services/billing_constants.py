from __future__ import annotations

ACTIVE_BILLING_STATUSES = frozenset({"active", "trialing", "past_due"})
FREE_PLAN_SLUG = "free"
ADMIN_PLAN_SLUG = "admin"
PLAN_KIND_INTERNAL = "internal"
PLAN_KIND_SUBSCRIPTION = "subscription"
PLAN_KIND_ADDON = "addon"
INTERNAL_PLAN_SLUGS = frozenset({FREE_PLAN_SLUG, ADMIN_PLAN_SLUG})
BILLING_PROVIDER = "whop"
