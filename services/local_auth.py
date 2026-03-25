"""Local email/password authentication helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional, Tuple

from store.models import UserAccount, _now

VALID_ROLES = ("Admin", "Compliance Officer", "Developer", "Researcher")
PASSWORD_MIN_LENGTH = 8
PBKDF2_ITERATIONS = 390_000


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    raw = str(password or "")
    if not raw:
        raise ValueError("Password is required.")
    salt = salt or os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, raw_iterations, salt_b64, digest_b64 = str(stored_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def validate_registration(email: str, password: str, confirm_password: str, role: str) -> Optional[str]:
    normalized_email = normalize_email(email)
    if not normalized_email:
        return "Email is required."
    if "@" not in normalized_email:
        return "Enter a valid email address."
    if len(str(password or "")) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if password != confirm_password:
        return "Passwords do not match."
    if role not in VALID_ROLES:
        return f"Role must be one of: {', '.join(VALID_ROLES)}."
    return None


def register_user(store, *, email: str, password: str, confirm_password: str, role: str, full_name: str = "") -> Tuple[bool, str, Optional[UserAccount]]:
    error = validate_registration(email, password, confirm_password, role)
    if error:
        return False, error, None

    normalized_email = normalize_email(email)
    if store.get_user_by_email(normalized_email):
        return False, "An account with that email already exists.", None

    now_ts = _now()
    user = UserAccount(
        email=normalized_email,
        password_hash=hash_password(password),
        role=role,
        full_name=str(full_name or "").strip(),
        created_at=now_ts,
        updated_at=now_ts,
    )
    created = store.create_user(user)
    return True, "Account created successfully.", created


def authenticate_user(store, *, email: str, password: str) -> Tuple[bool, str, Optional[UserAccount]]:
    normalized_email = normalize_email(email)
    user = store.get_user_by_email(normalized_email)
    if not user or not user.is_active:
        return False, "Invalid email or password.", None
    if not verify_password(password, user.password_hash):
        return False, "Invalid email or password.", None
    updated = store.update_user(user.id, last_login_at=_now())
    return True, "Signed in successfully.", updated or user
