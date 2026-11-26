import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.rate_limit_bucket import RateLimitBucket
from app.services.security import enforce_rate_limit, hash_security_identifier


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_concurrent_global_identity_rate_limit_is_atomic_across_ips():
    if not DATABASE_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not configured")

    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    scope = f"document_upload_concurrency_{suffix}"
    identity = f"user-{suffix}"
    client_ips = [f"203.0.113.{index + 1}" for index in range(12)]

    key_hashes = {
        hash_security_identifier(f"{scope}:identity:{identity.casefold()}"),
        *(
            hash_security_identifier(f"{scope}:ip:{client_ip}")
            for client_ip in client_ips
        ),
    }

    async def make_request(client_ip: str) -> bool:
        async with session_factory() as session:
            request = SimpleNamespace(
                client=SimpleNamespace(host=client_ip)
            )
            try:
                await enforce_rate_limit(
                    session,
                    request,
                    scope,
                    ip_limit=100,
                    identity=identity,
                    identity_limit=3,
                    identity_is_global=True,
                    window_seconds=3600,
                )
                return True
            except HTTPException as exc:
                assert exc.status_code == 429
                return False

    try:
        outcomes = await asyncio.gather(
            *(make_request(client_ip) for client_ip in client_ips)
        )

        # Different IPs must still contend for one atomic per-account bucket.
        assert sum(outcomes) == 3
        assert outcomes.count(False) == 9
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(RateLimitBucket).where(
                    RateLimitBucket.key_hash.in_(key_hashes)
                )
            )
            await session.commit()
        await engine.dispose()
