from pydantic import ValidationError

import pytest

from backend.app.schemas.auth import ChangePasswordRequest


def test_change_password_request_optional_confirm():
    req = ChangePasswordRequest(
        current_password="oldpass123",
        new_password="newpass123",
    )
    assert req.new_password == "newpass123"


def test_change_password_request_confirm_mismatch():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="oldpass123",
            new_password="newpass123",
            confirm_password="different",
        )
