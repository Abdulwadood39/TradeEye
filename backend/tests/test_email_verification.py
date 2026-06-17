from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api.deps import get_verified_user, raise_if_email_unverified


@pytest.mark.asyncio
async def test_get_verified_user_allows_verified_email():
    user = SimpleNamespace(email_verified_at="2026-01-01T00:00:00+00:00")
    assert await get_verified_user(user) is user


@pytest.mark.asyncio
async def test_get_verified_user_blocks_unverified_email():
    user = SimpleNamespace(email_verified_at=None)
    with pytest.raises(HTTPException) as exc:
        await get_verified_user(user)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "EMAIL_NOT_VERIFIED"


def test_raise_if_email_unverified_blocks_unverified_email():
    user = SimpleNamespace(email_verified_at=None)
    with pytest.raises(HTTPException) as exc:
        raise_if_email_unverified(user)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "EMAIL_NOT_VERIFIED"
