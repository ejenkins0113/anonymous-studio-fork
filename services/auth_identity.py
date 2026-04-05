"""Identity binding helpers for GUI authentication sources.

Break-glass is intentionally narrow:
- disabled by default
- only active in ANON_MODE=development unless explicitly overridden
- only honored for loopback requests
- always surfaced as auth_source="break_glass" for auditability
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from ipaddress import ip_address


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _is_loopback(remote_addr: str) -> bool:
    value = (remote_addr or "").strip()
    if not value:
        return False
    if value.startswith("::ffff:"):
        value = value.split("::ffff:", 1)[1]
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return value in {"localhost"}


@dataclass(frozen=True)
class BoundIdentity:
    user: str = ""
    email: str = ""
    groups: str = ""
    auth_source: str = "unauthenticated"

    @property
    def is_authenticated(self) -> bool:
        return self.auth_source in {"proxy", "break_glass"} and bool(self.user)


def bind_identity_from_request_headers(headers, remote_addr: str = "") -> BoundIdentity:
    """Bind GUI identity from trusted proxy headers or a gated break-glass env."""
    user = (headers.get("X-Auth-Request-User", "") or "").strip()
    email = (headers.get("X-Auth-Request-Email", "") or "").strip()
    groups = (headers.get("X-Auth-Request-Groups", "") or "").strip()
    if user:
        return BoundIdentity(
            user=user,
            email=email,
            groups=groups,
            auth_source="proxy",
        )

    if not _truthy_env("ANON_BREAK_GLASS_ENABLED", False):
        return BoundIdentity()
    if os.environ.get("ANON_MODE", "development").strip().lower() != "development":
        if not _truthy_env("ANON_BREAK_GLASS_ALLOW_NONDEV", False):
            return BoundIdentity()
    if not _is_loopback(remote_addr):
        return BoundIdentity()

    bg_user = (os.environ.get("ANON_BREAK_GLASS_USER", "") or "").strip()
    bg_email = (os.environ.get("ANON_BREAK_GLASS_EMAIL", "") or "").strip()
    bg_groups = (os.environ.get("ANON_BREAK_GLASS_GROUPS", "") or "").strip()
    if not bg_user and bg_email:
        bg_user = bg_email.split("@", 1)[0].strip()
    if not bg_email and bg_user:
        bg_email = f"{bg_user}@local.break-glass"
    if not bg_user:
        return BoundIdentity()

    return BoundIdentity(
        user=bg_user,
        email=bg_email,
        groups=bg_groups,
        auth_source="break_glass",
    )
