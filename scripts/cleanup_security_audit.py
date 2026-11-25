import argparse
import asyncio

from app.core.config import settings
from app.db.session import async_session_factory, engine
from app.services.audit_retention import purge_security_audit_events


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete security audit events older than the configured retention period."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=settings.security_audit_retention_days,
        help="Retention period in days (defaults to SECURITY_AUDIT_RETENTION_DAYS).",
    )
    args = parser.parse_args()
    if args.retention_days <= 0:
        parser.error("--retention-days must be greater than zero")

    async with async_session_factory() as db:
        deleted = await purge_security_audit_events(
            db, retention_days=args.retention_days
        )
    print(f"Deleted {deleted} security audit events older than {args.retention_days} days.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
