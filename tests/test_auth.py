import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_document_endpoints_require_authentication(unauthenticated_client):
    response = await unauthenticated_client.get("/documents/")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_register_login_and_get_current_user(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    registered = await unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "  USER@example.com ",
            "password": "a-long-test-password",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["email"] == "user@example.com"
    assert "hashed_password" not in registered.json()

    duplicate = await unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "another-long-password",
        },
    )
    assert duplicate.status_code == 409

    login = await unauthenticated_client.post(
        "/auth/login",
        data={
            "username": "USER@example.com",
            "password": "a-long-test-password",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    profile = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile.status_code == 200
    assert profile.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_login_rejects_incorrect_password(unauthenticated_client):
    await unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "person@example.com",
            "password": "correct-password-123",
        },
    )
    response = await unauthenticated_client.post(
        "/auth/login",
        data={
            "username": "person@example.com",
            "password": "incorrect-password",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_registration_rejects_short_password(unauthenticated_client):
    response = await unauthenticated_client.post(
        "/auth/register",
        json={"email": "person@example.com", "password": "short"},
    )
    assert response.status_code == 422
