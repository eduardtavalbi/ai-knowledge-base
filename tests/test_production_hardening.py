from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models.security_audit_event import SecurityAuditEvent
from app.services.audit_retention import purge_security_audit_events


def production_settings(**overrides):
    values = {
        "environment": "production",
        "debug": False,
        "auth_secret_key": "a-unique-production-secret-with-more-than-32-characters",
        "refresh_token_cookie_secure": True,
        "frontend_origins": "https://app.example.com",
        "frontend_public_url": "https://app.example.com",
        "database_url": "postgresql+asyncpg://mindbase:secure-db-password@db:5432/mindbase",
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
        {"database_url": "postgresql+asyncpg://mindbase:CHANGE_ME@db:5432/mindbase"},
        {"database_url": "postgresql+asyncpg:///mindbase"},
        {"email_verification_required": True},
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
