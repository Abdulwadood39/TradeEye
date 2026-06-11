from __future__ import annotations

import base64
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.app.core.config import get_settings

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        settings = get_settings()
        key = settings.encryption_key
        if not key:
            key = Fernet.generate_key().decode()
        elif len(key) != 44:
            key = base64.urlsafe_b64encode(key.encode()[:32].ljust(32, b"0")).decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
