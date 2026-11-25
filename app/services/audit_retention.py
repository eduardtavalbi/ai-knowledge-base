from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_audit_event import SecurityAuditEvent


async def purge_security_audit_events(
    db: AsyncSession,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    if retention_days <= 0:
        raise ValueError("retention_days must be greater than zero")
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    count = await db.scalar(
        select(func.count())
        .select_from(SecurityAuditEvent)
        .where(SecurityAuditEvent.created_at < cutoff)
    )
    await db.execute(
        delete(SecurityAuditEvent).where(SecurityAuditEvent.created_at < cutoff)
    )
    await db.commit()
    return int(count or 0)
