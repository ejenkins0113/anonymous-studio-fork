from __future__ import annotations

from services.local_auth import authenticate_user, hash_password, register_user, verify_password
from store.memory import MemoryStore


def test_hash_password_roundtrip():
    hashed = hash_password("Example123!")
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("Example123!", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_register_user_persists_hashed_password():
    store = MemoryStore(seed=False)
    ok, message, user = register_user(
        store,
        email="new.user@example.com",
        password="Example123!",
        confirm_password="Example123!",
        role="Developer",
        full_name="New User",
    )
    assert ok is True
    assert "successfully" in message.lower()
    saved = store.get_user_by_email("new.user@example.com")
    assert saved is not None
    assert saved.password_hash != "Example123!"
    assert verify_password("Example123!", saved.password_hash) is True


def test_authenticate_user_accepts_registered_credentials():
    store = MemoryStore(seed=False)
    register_user(
        store,
        email="new.user@example.com",
        password="Example123!",
        confirm_password="Example123!",
        role="Researcher",
        full_name="New User",
    )
    ok, message, user = authenticate_user(store, email="new.user@example.com", password="Example123!")
    assert ok is True
    assert "signed in" in message.lower()
    assert user is not None
    assert user.email == "new.user@example.com"


def test_register_user_rejects_duplicate_email():
    store = MemoryStore(seed=False)
    register_user(
        store,
        email="new.user@example.com",
        password="Example123!",
        confirm_password="Example123!",
        role="Researcher",
    )
    ok, message, _user = register_user(
        store,
        email="NEW.USER@example.com",
        password="Example123!",
        confirm_password="Example123!",
        role="Researcher",
    )
    assert ok is False
    assert "already exists" in message.lower()
