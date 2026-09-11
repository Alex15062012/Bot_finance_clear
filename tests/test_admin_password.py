from app.db.models.admin_user import hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("admin123")
    assert verify_password("admin123", hashed)
    assert not verify_password("wrong", hashed)
