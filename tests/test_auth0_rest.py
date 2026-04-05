from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, jsonify

from services.auth0_rest import Auth0JWTValidator, AuthError, install_auth0_bearer_auth


class _StubJwksClient:
    def __init__(self, key: str):
        self._key = key

    def get_signing_key_from_jwt(self, _token: str):
        return SimpleNamespace(key=self._key)


def _build_rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _build_token(
    *,
    private_key: str,
    audience: str,
    issuer: str,
    scope: str = "",
    ttl_seconds: int = 120,
) -> str:
    payload = {
        "sub": "auth0|abc123",
        "aud": audience,
        "iss": issuer,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    }
    if scope:
        payload["scope"] = scope
    return jwt.encode(payload, private_key, algorithm="RS256")


def _build_app(*, required_scopes=(), exempt_paths=()):
    app = Flask(__name__)

    @app.get("/private")
    def _private():
        return jsonify({"ok": True}), 200

    @app.get("/healthz")
    def _healthz():
        return jsonify({"ok": True}), 200

    private_key, public_key = _build_rsa_keypair()
    install_auth0_bearer_auth(
        app,
        domain="example.us.auth0.com",
        audience="https://anonymous-studio-api",
        algorithms=("RS256",),
        required_scopes=required_scopes,
        exempt_paths=exempt_paths,
        exempt_prefixes=(),
        jwks_client=_StubJwksClient(public_key),
    )

    return app, private_key


def test_header_parse_rejects_missing_authorization():
    with pytest.raises(AuthError):
        Auth0JWTValidator.get_token_auth_header(SimpleNamespace(headers={}))


def test_private_route_rejects_missing_bearer_token():
    app, _private_key = _build_app(exempt_paths=("/healthz",))
    client = app.test_client()

    response = client.get("/private")

    assert response.status_code == 401
    body = response.get_json()
    assert body["code"] == "authorization_header_missing"


def test_private_route_accepts_valid_token():
    app, private_key = _build_app(exempt_paths=("/healthz",))
    client = app.test_client()
    token = _build_token(
        private_key=private_key,
        audience="https://anonymous-studio-api",
        issuer="https://example.us.auth0.com/",
        scope="read:jobs",
    )

    response = client.get("/private", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_required_scope_is_enforced():
    app, private_key = _build_app(required_scopes=("read:jobs",), exempt_paths=("/healthz",))
    client = app.test_client()
    token = _build_token(
        private_key=private_key,
        audience="https://anonymous-studio-api",
        issuer="https://example.us.auth0.com/",
        scope="write:jobs",
    )

    response = client.get("/private", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    body = response.get_json()
    assert body["code"] == "insufficient_scope"


def test_exempt_path_skips_auth_check():
    app, _private_key = _build_app(exempt_paths=("/healthz",))
    client = app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200


def test_install_rejects_symmetric_algorithms():
    app = Flask(__name__)

    with pytest.raises(ValueError, match="HS256"):
        install_auth0_bearer_auth(
            app,
            domain="example.us.auth0.com",
            audience="https://anonymous-studio-api",
            algorithms=("HS256",),
        )
