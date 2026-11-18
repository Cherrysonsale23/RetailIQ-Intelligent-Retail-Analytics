from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def configure_auth(monkeypatch) -> str:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "unit-test-signing-secret-that-is-long-enough")
    monkeypatch.setenv("SUPABASE_JWT_JWKS_URL", "")
    get_settings.cache_clear()
    return "unit-test-signing-secret-that-is-long-enough"


def token(secret: str, *, expires: datetime | None = None) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "email": "analyst@example.test",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "iat": now,
            "exp": expires or now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )


def test_health_is_public() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_identity_requires_bearer_token() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_identity_returns_verified_claims(monkeypatch) -> None:
    secret = configure_auth(monkeypatch)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token(secret)}"})
    assert response.status_code == 200
    assert response.json() == {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "email": "analyst@example.test"}
    get_settings.cache_clear()


def test_identity_rejects_expired_token(monkeypatch) -> None:
    secret = configure_auth(monkeypatch)
    expired = token(secret, expires=datetime.now(UTC) - timedelta(minutes=1))
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    get_settings.cache_clear()


def test_dataset_apis_require_authentication() -> None:
    assert client.get("/api/v1/datasets").status_code == 401
    assert client.get("/api/v1/datasets/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/analytics/overview").status_code == 401
