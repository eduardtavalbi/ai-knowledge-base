from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models.rate_limit_bucket import RateLimitBucket
from app.models.security_audit_event import SecurityAuditEvent
from app.services.audit_retention import purge_security_audit_events
from app.services.security import enforce_rate_limit


def production_settings(**overrides):
    values = {
        "environment": "production",
        "debug": False,
        "auth_secret_key": "a-unique-production-secret-with-more-than-32-characters",
        "refresh_token_cookie_secure": True,
        "frontend_origins": "https://app.example.com",
        "frontend_public_url": "https://app.example.com",
        "database_url": "postgresql+asyncpg://mindbase:secure-db-password@db:5432/mindbase",
        "smtp_host": "smtp.example.com",
        "smtp_from_email": "noreply@example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_configuration_accepts_secure_values():
    assert production_settings().environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"debug": True},
        {"auth_secret_key": "CHANGE_ME_USE_A_RANDOM_SECRET_AT_LEAST_32_CHARACTERS"},
        {"auth_secret_key": "too-short"},
        {"refresh_token_cookie_secure": False},
        {"frontend_origins": "http://app.example.com"},
        {"frontend_origins": "https://app.example.com/path"},
        {"frontend_public_url": "https://"},
        {"frontend_public_url": "http://app.example.com"},
        {"frontend_public_url": "https://app.example.com:invalid"},
        {"frontend_origins": "https://app.example.com:99999"},
        {"database_url": "postgresql+asyncpg://mindbase:CHANGE_ME@db:5432/mindbase"},
        {"database_url": "postgresql+asyncpg:///mindbase"},
        {"smtp_host": ""},
        {"smtp_from_email": ""},
        {
            "email_verification_required": True,
            "smtp_host": "smtp.example.com",
            "smtp_from_email": "noreply@example.com",
            "smtp_username": "mailer",
            "smtp_password": "",
        },
    ],
)
def test_production_configuration_rejects_unsafe_values(overrides):
    with pytest.raises(ValidationError):
        production_settings(**overrides)


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging")


def test_smtp_transport_modes_are_mutually_exclusive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_starttls=True, smtp_use_ssl=True)


def test_production_smtp_requires_encryption():
    with pytest.raises(ValidationError):
        production_settings(smtp_starttls=False, smtp_use_ssl=False)


@pytest.mark.asyncio
async def test_audit_retention_deletes_only_expired_events():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add_all(
            [
                SecurityAuditEvent(event_type="old", created_at=now - timedelta(days=91)),
                SecurityAuditEvent(event_type="boundary", created_at=now - timedelta(days=90)),
                SecurityAuditEvent(event_type="new", created_at=now - timedelta(days=1)),
            ]
        )
        await db.commit()
        deleted = await purge_security_audit_events(
            db, retention_days=90, now=now
        )
        remaining = list((await db.scalars(
            select(SecurityAuditEvent)
        )).all())
    assert deleted == 1
    assert {event.event_type for event in remaining} == {"boundary", "new"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_retention_requires_positive_days():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        with pytest.raises(ValueError):
            await purge_security_audit_events(db, retention_days=0)
    await engine.dispose()


@pytest.mark.asyncio
async def test_readiness_endpoint_reports_database_ready(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_503_when_database_is_unavailable(client):
    from app.db.session import get_db
    from app.main import app

    class UnavailableDatabase:
        async def execute(self, statement):
            raise RuntimeError("database connection failed")

    async def override_unavailable_db():
        yield UnavailableDatabase()

    app.dependency_overrides[get_db] = override_unavailable_db
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}



@pytest.mark.asyncio
async def test_global_identity_rate_limit_applies_across_client_ips():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        first_request = SimpleNamespace(
            client=SimpleNamespace(host="192.0.2.10")
        )
        second_request = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.20")
        )

        await enforce_rate_limit(
            db,
            first_request,
            "document_upload",
            ip_limit=10,
            identity="user-42",
            identity_limit=1,
            identity_is_global=True,
            window_seconds=3600,
        )

        with pytest.raises(HTTPException) as error:
            await enforce_rate_limit(
                db,
                second_request,
                "document_upload",
                ip_limit=10,
                identity="user-42",
                identity_limit=1,
                identity_is_global=True,
                window_seconds=3600,
            )

    assert error.value.status_code == 429
    await engine.dispose()


@pytest.mark.asyncio
async def test_identity_rate_limit_remains_ip_scoped_by_default():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        for client_ip in ("192.0.2.10", "198.51.100.20"):
            await enforce_rate_limit(
                db,
                SimpleNamespace(client=SimpleNamespace(host=client_ip)),
                "login",
                ip_limit=10,
                identity="same-email@example.com",
                identity_limit=1,
                window_seconds=3600,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_delayed_rate_limit_request_cannot_move_bucket_to_an_older_window(monkeypatch):
    from app.services import security

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    moments = iter(
        [
            datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 1, 1, tzinfo=timezone.utc),
        ]
    )

    class ControlledDateTime:
        @classmethod
        def now(cls, tz=None):
            return next(moments)

        @staticmethod
        def fromtimestamp(value, tz=None):
            return datetime.fromtimestamp(value, tz)

    monkeypatch.setattr(security, "datetime", ControlledDateTime)
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.55"))

    async with session_factory() as db:
        for _ in range(4):
            await security.enforce_rate_limit(
                db,
                request,
                "window_boundary",
                ip_limit=10,
                window_seconds=60,
            )

        bucket = await db.get(
            RateLimitBucket,
            security.hash_security_identifier("window_boundary:ip:192.0.2.55"),
        )

    assert bucket is not None
    assert bucket.window_started_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc
    )
    assert bucket.request_count == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_retry_after_uses_active_window_for_delayed_request(monkeypatch):
    from app.services import security

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    moments = iter(
        [
            datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 0, 59, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 12, 1, 2, tzinfo=timezone.utc),
        ]
    )

    class ControlledDateTime:
        @classmethod
        def now(cls, tz=None):
            return next(moments)

        @staticmethod
        def fromtimestamp(value, tz=None):
            return datetime.fromtimestamp(value, tz)

    monkeypatch.setattr(security, "datetime", ControlledDateTime)
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.56"))

    async with session_factory() as db:
        for _ in range(3):
            await security.enforce_rate_limit(
                db,
                request,
                "delayed_retry_after",
                ip_limit=2,
                window_seconds=60,
            )

        with pytest.raises(HTTPException) as error:
            await security.enforce_rate_limit(
                db,
                request,
                "delayed_retry_after",
                ip_limit=2,
                window_seconds=60,
            )

        bucket = await db.get(
            RateLimitBucket,
            security.hash_security_identifier(
                "delayed_retry_after:ip:192.0.2.56"
            ),
        )

    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "59"
    assert bucket is not None
    assert bucket.window_started_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc
    )
    assert bucket.request_count == 3
    await engine.dispose()

