import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.rate_limit_bucket import RateLimitBucket
from app.models.security_audit_event import SecurityAuditEvent


def hash_security_identifier(value: str) -> str:
    """Return a keyed digest for an identifier used in security audit records."""
    return hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _digest(value: str) -> str:
    return hash_security_identifier(value)


async def enforce_rate_limit(
    db: AsyncSession,
    request: Request,
    scope: str,
    *,
    ip_limit: int,
    window_seconds: int,
    identity: str | None = None,
    identity_limit: int | None = None,
    identity_is_global: bool = False,
) -> None:
    now = datetime.now(timezone.utc)
    window_start = datetime.fromtimestamp(
        int(now.timestamp()) // window_seconds * window_seconds,
        tz=timezone.utc,
    )
    client_ip = request.client.host if request.client else "unknown"
    dimensions = [("ip", client_ip, ip_limit)]
    if identity is not None and identity_limit is not None:
        if identity_is_global:
            dimensions.append(("identity", identity.casefold(), identity_limit))
        else:
            dimensions.append(("identity_ip", f"{identity.casefold()}:{client_ip}", identity_limit))

    dialect = db.get_bind().dialect.name
    insert_statement = pg_insert if dialect == "postgresql" else sqlite_insert
    exceeded = False
    retry_after = 1

    for dimension, value, limit in dimensions:
        key_hash = _digest(f"{scope}:{dimension}:{value}")
        statement = insert_statement(RateLimitBucket).values(
            key_hash=key_hash,
            window_started_at=window_start,
            request_count=1,
        )
        same_window = RateLimitBucket.window_started_at == window_start
        newer_window_exists = RateLimitBucket.window_started_at > window_start
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimitBucket.key_hash],
            set_={
                # A delayed request from an older window must never move the
                # bucket backwards after a newer window has already started.
                "window_started_at": case(
                    (newer_window_exists, RateLimitBucket.window_started_at),
                    else_=window_start,
                ),
                "request_count": case(
                    (same_window, RateLimitBucket.request_count + 1),
                    (newer_window_exists, RateLimitBucket.request_count),
                    else_=1,
                ),
            },
        ).returning(RateLimitBucket.request_count)
        count = (await db.execute(statement)).scalar_one()
        if count > limit:
            exceeded = True
            retry_after = max(
                retry_after,
                int((window_start + timedelta(seconds=window_seconds) - now).total_seconds()) + 1,
            )

    await db.execute(delete(RateLimitBucket).where(RateLimitBucket.window_started_at < now - timedelta(days=1)))
    await db.commit()
    if exceeded:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


async def record_security_event(
    db: AsyncSession,
    event_type: str,
    request: Request,
    *,
    email: str | None = None,
    user_id: int | None = None,
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    db.add(SecurityAuditEvent(
        event_type=event_type,
        user_id=user_id,
        email_hash=_digest(email.casefold()) if email else None,
        ip_hash=_digest(client_ip),
        user_agent_hash=_digest(user_agent) if user_agent else None,
    ))
    await db.commit()
