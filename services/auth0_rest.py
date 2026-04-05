"""Auth0 JWT validation for Flask-based REST services.

Security design notes
---------------------
* Only asymmetric algorithms from ASYMMETRIC_ALGS_ALLOWLIST are accepted.
  HS256 and ``alg: none`` are rejected at construction time, so a
  misconfigured environment variable causes a hard startup failure rather than
  a silent per-request security downgrade.
* PyJWKClient is created with an explicit timeout so a slow or unreachable
  Auth0 JWKS endpoint cannot hold a request thread open indefinitely.
* Distinct JWT exception types are caught separately so that SIEM log streams
  can distinguish forged-signature events from ordinary expiry or bad headers.
* Scope enforcement error messages are intentionally generic to avoid leaking
  the internal permission model to callers.
"""
from __future__ import annotations

import logging
import os
import re
from functools import wraps
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional, Sequence

import jwt
from flask import Flask, Request, g, jsonify, request

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Algorithm security allowlist
# ---------------------------------------------------------------------------
# Only asymmetric (public-key) algorithms are accepted.  Symmetric algorithms
# (HS256/384/512) require sharing the signing secret with every verifier,
# which is incompatible with the Auth0 JWKS trust model.  ``none`` bypasses
# signature verification entirely.  PS* (RSASSA-PSS) variants are included so
# operators can adopt stronger key sizes without a code change.
ASYMMETRIC_ALGS_ALLOWLIST: frozenset[str] = frozenset({
    "RS256", "RS384", "RS512",
    "ES256", "ES384", "ES512",
    "PS256", "PS384", "PS512",
})

# Default HTTPS timeout (seconds) for JWKS endpoint fetches.
_JWKS_TIMEOUT_SECONDS: int = 10


def _truthy_env(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _split_csv_or_space(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    values = [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]
    return tuple(values)


def _normalize_auth0_domain(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    return value.strip().strip("/")


def _validate_algorithms(algorithms: Sequence[str]) -> tuple[str, ...]:
    """Enforce the asymmetric allowlist; raise ValueError on any forbidden algorithm.

    A misconfigured ANON_AUTH_JWT_ALGORITHMS env var is a hard startup failure,
    not a silent per-request bypass.
    """
    validated: list[str] = []
    for alg in algorithms:
        normalized = alg.strip().upper()
        match = next((a for a in ASYMMETRIC_ALGS_ALLOWLIST if a.upper() == normalized), None)
        if match is None:
            raise ValueError(
                f"Algorithm '{alg}' is not in the asymmetric allowlist "
                f"({', '.join(sorted(ASYMMETRIC_ALGS_ALLOWLIST))}). "
                "Symmetric algorithms (HS*) and 'none' are never permitted."
            )
        validated.append(match)
    if not validated:
        raise ValueError("At least one asymmetric algorithm must be configured.")
    return tuple(validated)


@dataclass(frozen=True)
class AuthError(Exception):
    status_code: int
    code: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "description": self.description}


class Auth0JWTValidator:
    """Validate Auth0-issued JWT access tokens against JWKS.

    All token claims (iss, aud, exp, nbf, alg) are enforced by PyJWT.
    Algorithm confusion is prevented by construction: only algorithms in
    ASYMMETRIC_ALGS_ALLOWLIST can be instantiated.
    """

    def __init__(
        self,
        *,
        domain: str,
        audience: str,
        algorithms: Sequence[str] = ("RS256",),
        required_scopes: Iterable[str] = (),
        jwks_client: object | None = None,
    ) -> None:
        normalized_domain = _normalize_auth0_domain(domain)
        if not normalized_domain:
            raise ValueError("AUTH0_DOMAIN is required when auth is enabled.")
        if not (audience or "").strip():
            raise ValueError("AUTH0_API_AUDIENCE is required when auth is enabled.")

        # Raises ValueError on any forbidden algorithm — fail fast at startup.
        validated_algorithms = _validate_algorithms(algorithms)

        self.domain = normalized_domain
        self.audience = audience.strip()
        self.algorithms = validated_algorithms
        self.required_scopes = tuple(scope for scope in required_scopes if scope)
        self.issuer = f"https://{self.domain}/"
        self.jwks_url = urljoin(self.issuer, ".well-known/jwks.json")

        if jwks_client is not None:
            self._jwks_client = jwks_client
        else:
            # Explicit timeout prevents JWKS fetch from blocking a thread
            # indefinitely when Auth0 is slow or unreachable.
            self._jwks_client = jwt.PyJWKClient(
                self.jwks_url,
                timeout=_JWKS_TIMEOUT_SECONDS,
            )

    @staticmethod
    def get_token_auth_header(req: Request) -> str:
        auth = req.headers.get("Authorization", None)
        if not auth:
            raise AuthError(
                status_code=401,
                code="authorization_header_missing",
                description="Authorization header is expected",
            )

        parts = auth.split()
        if parts[0].lower() != "bearer":
            raise AuthError(
                status_code=401,
                code="invalid_header",
                description="Authorization header must start with Bearer",
            )
        if len(parts) == 1:
            raise AuthError(status_code=401, code="invalid_header", description="Token not found")
        if len(parts) > 2:
            raise AuthError(
                status_code=401,
                code="invalid_header",
                description="Authorization header must be Bearer token",
            )
        return parts[1]

    def decode_token(self, token: str) -> Mapping[str, object]:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
            )
            return payload
        except jwt.ExpiredSignatureError as ex:
            raise AuthError(
                status_code=401, code="token_expired", description="Token is expired"
            ) from ex
        except jwt.InvalidAudienceError as ex:
            raise AuthError(
                status_code=401, code="invalid_audience", description="Incorrect audience"
            ) from ex
        except jwt.InvalidIssuerError as ex:
            raise AuthError(
                status_code=401, code="invalid_issuer", description="Incorrect issuer"
            ) from ex
        except jwt.InvalidSignatureError as ex:
            # Log at WARNING so SIEM/alerting can distinguish forged tokens from
            # ordinary expiry or misconfiguration.
            _log.warning("JWT signature validation failed (possible token forgery attempt)")
            raise AuthError(
                status_code=401,
                code="invalid_token",
                description="Token signature is invalid",
            ) from ex
        except jwt.InvalidAlgorithmError as ex:
            _log.warning("JWT algorithm not in allowlist: %s", type(ex).__name__)
            raise AuthError(
                status_code=401,
                code="invalid_token",
                description="Token algorithm is not permitted",
            ) from ex
        except jwt.DecodeError as ex:
            raise AuthError(
                status_code=401,
                code="invalid_token",
                description="Token could not be decoded",
            ) from ex
        except Exception as ex:
            # PyJWKClient fetch errors (network, bad JSON) land here.  Log the
            # full exception internally but never surface it to the caller.
            _log.exception("Unexpected error during JWT validation: %s", type(ex).__name__)
            raise AuthError(
                status_code=401,
                code="invalid_token",
                description="Token validation failed",
            ) from ex

    def _assert_scopes(self, payload: Mapping[str, object]) -> None:
        if not self.required_scopes:
            return
        scope_str = str(payload.get("scope", "") or "")
        granted = set(scope_str.split())
        missing = [scope for scope in self.required_scopes if scope not in granted]
        if missing:
            # Do not enumerate missing scope names in the client-visible
            # description — that leaks the permission model. Log detail server-side.
            _log.info("Token rejected: missing required scope(s): %s", " ".join(missing))
            raise AuthError(
                status_code=403,
                code="insufficient_scope",
                description="Insufficient permissions",
            )

    def validate_request(self, req: Request) -> Mapping[str, object]:
        token = self.get_token_auth_header(req)
        payload = self.decode_token(token)
        self._assert_scopes(payload)
        return payload


def install_auth0_bearer_auth(
    app: Flask,
    *,
    domain: str,
    audience: str,
    algorithms: Sequence[str] = ("RS256",),
    required_scopes: Iterable[str] = (),
    exempt_paths: Sequence[str] = (),
    exempt_prefixes: Sequence[str] = (),
    jwks_client: object | None = None,
) -> Auth0JWTValidator:
    """Install Auth0 Bearer JWT authentication as a Flask before_request hook.

    Construction raises ValueError immediately if the configuration is invalid
    (bad domain, missing audience, or forbidden algorithm), so misconfiguration
    is a startup failure rather than a per-request failure.
    """
    validator = Auth0JWTValidator(
        domain=domain,
        audience=audience,
        algorithms=algorithms,
        required_scopes=required_scopes,
        jwks_client=jwks_client,
    )
    exact = set(exempt_paths)
    prefixes = tuple(exempt_prefixes)

    @app.errorhandler(AuthError)
    def _handle_auth_error(ex: AuthError):
        response = jsonify(ex.to_dict())
        response.status_code = ex.status_code
        return response

    @app.before_request
    def _check_auth():
        # CORS preflight must pass through so the browser can negotiate headers
        # before the credentialed request. The actual request is still validated.
        if request.method == "OPTIONS":
            return None
        path = request.path or "/"
        if path in exact:
            return None
        if prefixes and any(path.startswith(prefix) for prefix in prefixes):
            return None
        g.auth_payload = validator.validate_request(request)
        return None

    _log.info(
        "Auth0 REST auth enabled (issuer=%s audience=%s algorithms=%s)",
        validator.issuer,
        validator.audience,
        ",".join(validator.algorithms),
    )
    return validator


def maybe_enable_auth0_rest_auth(app: Flask) -> bool:
    """Enable Auth0 JWT auth for a Flask app when ANON_AUTH_ENABLED=1.

    Returns True if auth was installed, False if disabled.  Raises ValueError
    at startup if the algorithm configuration is invalid.
    """
    if not _truthy_env("ANON_AUTH_ENABLED", default=False):
        return False

    domain = os.environ.get("AUTH0_DOMAIN", "")
    audience = os.environ.get("AUTH0_API_AUDIENCE", "")

    # _validate_algorithms() (inside Auth0JWTValidator.__init__) will raise
    # ValueError on HS256 / none, terminating startup on misconfiguration.
    raw_algs = os.environ.get("ANON_AUTH_JWT_ALGORITHMS", "RS256")
    algorithms = _split_csv_or_space(raw_algs) or ("RS256",)

    required_scopes = _split_csv_or_space(os.environ.get("ANON_AUTH_REQUIRED_SCOPES", ""))
    exempt_paths = _split_csv_or_space(os.environ.get("ANON_AUTH_EXEMPT_PATHS", ""))
    exempt_prefixes = _split_csv_or_space(os.environ.get("ANON_AUTH_EXEMPT_PREFIXES", ""))

    install_auth0_bearer_auth(
        app,
        domain=domain,
        audience=audience,
        algorithms=algorithms,
        required_scopes=required_scopes,
        exempt_paths=exempt_paths,
        exempt_prefixes=exempt_prefixes,
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# RBAC — Role-based access control via Auth0 permissions/scopes
# ─────────────────────────────────────────────────────────────────────────────

# Well-known permission names used throughout the app
PERMISSIONS = {
    # PII anonymization
    "pii:read":      "View anonymization results",
    "pii:write":     "Submit anonymization jobs",
    "pii:delete":    "Delete anonymization results",
    # Pipeline management
    "pipeline:read":  "View pipeline cards",
    "pipeline:write": "Create/update pipeline cards",
    "pipeline:attest": "Attest compliance on pipeline cards",
    # Scheduling
    "schedule:read":  "View appointments",
    "schedule:write": "Create/update appointments",
    "schedule:delete": "Delete appointments",
    # Audit
    "audit:read":     "View audit logs",
    # Admin
    "admin:read":     "View admin settings",
    "admin:write":    "Modify admin settings",
}


def get_user_permissions() -> set[str]:
    """Extract permissions from the current request's JWT payload.

    Auth0 can include permissions in tokens via:
      - `scope` claim (space-delimited scopes)
      - `permissions` claim (array, when RBAC is enabled in Auth0 API settings)

    Returns a set of permission strings granted to the current user.
    """
    payload = getattr(g, "auth_payload", None) or {}
    permissions: set[str] = set()

    # From scope claim (standard OAuth2)
    scope_str = str(payload.get("scope", "") or "")
    permissions.update(scope_str.split())

    # From permissions claim (Auth0 RBAC)
    perms_claim = payload.get("permissions", [])
    if isinstance(perms_claim, list):
        permissions.update(p for p in perms_claim if isinstance(p, str) and p)

    return permissions


def has_permission(permission: str) -> bool:
    """Check if the current user has a specific permission."""
    return permission in get_user_permissions()


def has_any_permission(*permissions: str) -> bool:
    """Check if the current user has at least one of the specified permissions."""
    granted = get_user_permissions()
    return bool(granted & set(permissions))


def has_all_permissions(*permissions: str) -> bool:
    """Check if the current user has all of the specified permissions."""
    granted = get_user_permissions()
    return set(permissions) <= granted


def require_permission(*permissions: str, require_all: bool = False) -> Callable:
    """Decorator to enforce permission checks on Flask route handlers.

    Args:
        permissions: One or more permission strings to check.
        require_all: If True, ALL permissions must be present. Default is ANY.

    Usage:
        @app.get("/admin/settings")
        @require_permission("admin:read")
        def get_settings():
            ...

        @app.post("/pipeline/attest")
        @require_permission("pipeline:write", "pipeline:attest", require_all=True)
        def attest_card():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if require_all:
                check_result = has_all_permissions(*permissions)
                log_msg = "Access denied: user missing required permissions %s"
            else:
                check_result = has_any_permission(*permissions)
                log_msg = "Access denied: user missing any of permissions %s"

            if not check_result:
                _log.info(log_msg, permissions)
                raise AuthError(
                    status_code=403,
                    code="insufficient_permissions",
                    description="Insufficient permissions",
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user_id() -> Optional[str]:
    """Extract the user identifier (sub claim) from the current JWT."""
    payload = getattr(g, "auth_payload", None) or {}
    return payload.get("sub")


def get_current_user_email() -> Optional[str]:
    """Extract user email from JWT (if present in claims)."""
    payload = getattr(g, "auth_payload", None) or {}
    # Auth0 may include email in various claims depending on configuration
    return payload.get("email") or payload.get("https://anon-studio/email")


# ─────────────────────────────────────────────────────────────────────────────
# Compliance Audit Logging — security events for SIEM integration
# ─────────────────────────────────────────────────────────────────────────────

# Callback for compliance audit logging (set by app.py to route to store)
_compliance_audit_callback: Optional[Callable[[str, str, str, str, str, str], None]] = None


def set_compliance_audit_callback(
    callback: Callable[[str, str, str, str, str, str], None]
) -> None:
    """Register the compliance audit callback (typically store.log_user_action).

    Signature: callback(actor, action, resource_type, resource_id, details, severity)
    """
    global _compliance_audit_callback
    _compliance_audit_callback = callback
    _log.info("Compliance audit callback registered")


def log_auth_event(
    action: str,
    resource_type: str = "auth",
    resource_id: str = "",
    details: str = "",
    severity: str = "info",
) -> None:
    """Log an authentication/authorization event to the compliance audit trail.

    This sends events to both:
      - Python logging (for SIEM/log aggregation)
      - Store audit log (for in-app compliance dashboard)

    Args:
        action: Event type (e.g., "auth.login", "auth.denied", "rbac.check_failed")
        resource_type: Resource category (default: "auth")
        resource_id: Optional resource identifier
        details: Human-readable event details
        severity: One of "info", "warning", "error", "critical"
    """
    user_id = get_current_user_id() or "anonymous"

    # Always log to Python logger for SIEM integration
    log_msg = f"[COMPLIANCE] actor={user_id} action={action} resource={resource_type}/{resource_id} {details}"
    if severity == "critical":
        _log.critical(log_msg)
    elif severity == "error":
        _log.error(log_msg)
    elif severity == "warning":
        _log.warning(log_msg)
    else:
        _log.info(log_msg)

    # Also send to store audit log if callback is registered
    if _compliance_audit_callback:
        try:
            _compliance_audit_callback(
                user_id, action, resource_type, resource_id, details, severity
            )
        except Exception as exc:
            _log.warning("Failed to write compliance audit entry: %s", exc)


def log_permission_check(permission: str, granted: bool) -> None:
    """Log an RBAC permission check for compliance auditing."""
    result = "granted" if granted else "denied"
    log_auth_event(
        action=f"rbac.{result}",
        resource_type="permission",
        resource_id=permission,
        details=f"Permission check: {permission} -> {result}",
        severity="info" if granted else "warning",
    )
