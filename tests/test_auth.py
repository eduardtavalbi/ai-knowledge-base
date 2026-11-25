import jwt
import pytest

from app.api import auth as auth_module
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


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_revokes_session(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(auth_module, "REFRESH_TOKEN_REUSE_GRACE_SECONDS", 0)
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "rotation@example.com", "password": "a-long-test-password"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "rotation@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    access_token = login.json()["access_token"]
    old_refresh_token = unauthenticated_client.cookies.get("mindbase_refresh")
    assert old_refresh_token

    rotated = await unauthenticated_client.post("/auth/refresh")
    assert rotated.status_code == 200
    assert rotated.headers["cache-control"] == "no-store"
    new_refresh_token = unauthenticated_client.cookies.get("mindbase_refresh")
    assert new_refresh_token and new_refresh_token != old_refresh_token

    replay = await unauthenticated_client.post(
        "/auth/refresh",
        headers={"Cookie": f"mindbase_refresh={old_refresh_token}"},
    )
    assert replay.status_code == 401
    profile = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
    )
    assert profile.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh_session(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "logout@example.com", "password": "a-long-test-password"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "logout@example.com", "password": "a-long-test-password"},
    )
    access_token = login.json()["access_token"]

    logged_out = await unauthenticated_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logged_out.status_code == 204

    profile = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert profile.status_code == 401
    refreshed = await unauthenticated_client.post("/auth/refresh")
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_user_can_list_and_revoke_only_own_sessions(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "sessions@example.com", "password": "a-long-test-password"},
    )
    first_login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "sessions@example.com", "password": "a-long-test-password"},
    )
    first_token = first_login.json()["access_token"]
    second_login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "sessions@example.com", "password": "a-long-test-password"},
    )
    second_session_token = second_login.json()["access_token"]
    second_session_id = jwt.decode(
        second_session_token,
        settings.auth_secret_key,
        algorithms=["HS256"],
    )["sid"]

    sessions = await unauthenticated_client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) == 2

    session_to_revoke = second_session_id
    revoked = await unauthenticated_client.delete(
        f"/auth/sessions/{session_to_revoke}",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert revoked.status_code == 204

    remaining = await unauthenticated_client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert remaining.status_code == 200
    assert len(remaining.json()) == 1
    revoked_session_profile = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {second_session_token}"},
    )
    assert revoked_session_profile.status_code == 401

    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "another-user@example.com", "password": "a-long-test-password"},
    )
    another_login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "another-user@example.com", "password": "a-long-test-password"},
    )
    another_token = another_login.json()["access_token"]
    another_session_id = jwt.decode(
        another_token,
        settings.auth_secret_key,
        algorithms=["HS256"],
    )["sid"]

    cross_user_revoke = await unauthenticated_client.delete(
        f"/auth/sessions/{another_session_id}",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert cross_user_revoke.status_code == 404
    another_profile = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {another_token}"},
    )
    assert another_profile.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_session_even_after_access_token_expiry(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "expired-logout@example.com", "password": "a-long-test-password"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "expired-logout@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200
    payload = jwt.decode(
        login.json()["access_token"],
        settings.auth_secret_key,
        algorithms=["HS256"],
    )
    payload["exp"] = 1
    expired_access_token = jwt.encode(
        payload,
        settings.auth_secret_key,
        algorithm="HS256",
    )

    logged_out = await unauthenticated_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {expired_access_token}"},
    )
    assert logged_out.status_code == 204

    refresh = await unauthenticated_client.post("/auth/refresh")
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_untrusted_browser_origin(unauthenticated_client):
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "origin@example.com", "password": "a-long-test-password"},
    )
    response = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "origin@example.com", "password": "a-long-test-password"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert "mindbase_refresh" not in unauthenticated_client.cookies


@pytest.mark.asyncio
async def test_refresh_rejects_untrusted_browser_origin(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "refresh-origin@example.com", "password": "a-long-test-password"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "refresh-origin@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200

    rejected = await unauthenticated_client.post(
        "/auth/refresh",
        headers={"Origin": "https://attacker.example"},
    )
    assert rejected.status_code == 403

    accepted = await unauthenticated_client.post("/auth/refresh")
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_recent_refresh_reuse_can_retry_with_rotated_cookie(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "parallel-refresh@example.com", "password": "a-long-test-password"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "parallel-refresh@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200
    stale_cookie = unauthenticated_client.cookies.get("mindbase_refresh")

    first_refresh = await unauthenticated_client.post("/auth/refresh")
    assert first_refresh.status_code == 200
    rotated_cookie = unauthenticated_client.cookies.get("mindbase_refresh")
    assert rotated_cookie and rotated_cookie != stale_cookie

    concurrent_refresh = await unauthenticated_client.post(
        "/auth/refresh",
        headers={"Cookie": f"mindbase_refresh={stale_cookie}"},
    )
    assert concurrent_refresh.status_code == 409

    retry = await unauthenticated_client.post("/auth/refresh")
    assert retry.status_code == 200



@pytest.mark.asyncio
async def test_email_verification_is_required_when_enabled(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    monkeypatch.setattr(settings, "email_verification_required", True)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.test")
    sent = []

    async def fake_send_email(recipient, subject, body):
        sent.append((recipient, subject, body))

    monkeypatch.setattr(auth_module, "send_account_email", fake_send_email)

    registered = await unauthenticated_client.post(
        "/auth/register",
        json={"email": "verify@example.com", "password": "a-long-test-password"},
    )
    assert registered.status_code == 201
    assert len(sent) == 1
    assert "verify=" in sent[0][2]

    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "verify@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 403

    import re
    token = re.search(r"verify=([A-Za-z0-9_-]+)", sent[0][2]).group(1)
    verified = await unauthenticated_client.post(
        "/auth/verify-email",
        json={"token": token},
    )
    assert verified.status_code == 200
    assert verified.json()["email"] == "verify@example.com"

    login_after_verification = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "verify@example.com", "password": "a-long-test-password"},
    )
    assert login_after_verification.status_code == 200

    replay = await unauthenticated_client.post(
        "/auth/verify-email",
        json={"token": token},
    )
    assert replay.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_is_one_time_and_revokes_existing_sessions(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-that-is-long-enough-for-hmac",
    )
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.test")
    sent = []

    async def fake_send_email(recipient, subject, body):
        sent.append((recipient, subject, body))

    monkeypatch.setattr(auth_module, "send_account_email", fake_send_email)

    await unauthenticated_client.post(
        "/auth/register",
        json={"email": "reset@example.com", "password": "old-password-123"},
    )
    login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "reset@example.com", "password": "old-password-123"},
    )
    assert login.status_code == 200
    old_access_token = login.json()["access_token"]

    requested = await unauthenticated_client.post(
        "/auth/forgot-password",
        json={"email": "reset@example.com"},
    )
    assert requested.status_code == 202
    assert len(sent) == 1

    import re
    token = re.search(r"reset=([A-Za-z0-9_-]+)", sent[0][2]).group(1)
    reset = await unauthenticated_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "new-password-456"},
    )
    assert reset.status_code == 204

    old_session = await unauthenticated_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert old_session.status_code == 401

    replay = await unauthenticated_client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "another-password-789"},
    )
    assert replay.status_code == 400

    old_password_login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "reset@example.com", "password": "old-password-123"},
    )
    assert old_password_login.status_code == 401
    new_password_login = await unauthenticated_client.post(
        "/auth/login",
        data={"username": "reset@example.com", "password": "new-password-456"},
    )
    assert new_password_login.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_does_not_disclose_unknown_email(unauthenticated_client, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.test")
    sent = []

    async def fake_send_email(recipient, subject, body):
        sent.append(recipient)

    monkeypatch.setattr(auth_module, "send_account_email", fake_send_email)

    known = await unauthenticated_client.post(
        "/auth/forgot-password",
        json={"email": "known@example.com"},
    )
    unknown = await unauthenticated_client.post(
        "/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert sent == []
