from backend.app.core.security import generate_token, hash_password, hash_token, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("securepassword123")
    assert verify_password("securepassword123", hashed)
    assert not verify_password("wrong", hashed)


def test_token_hash_deterministic():
    raw = generate_token()
    assert hash_token(raw) == hash_token(raw)
    assert hash_token(raw) != hash_token(generate_token())
