import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_applied_migrations_allow_identical_content_for_different_users():
    if not DATABASE_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not configured")

    engine = create_async_engine(DATABASE_URL)
    transaction = None
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            suffix = uuid.uuid4().hex
            first_user_id = (
                await connection.execute(
                    text(
                        "INSERT INTO users (email, hashed_password) "
                        "VALUES (:email, 'unused') RETURNING id"
                    ),
                    {"email": f"migration-first-{suffix}@example.com"},
                )
            ).scalar_one()
            second_user_id = (
                await connection.execute(
                    text(
                        "INSERT INTO users (email, hashed_password) "
                        "VALUES (:email, 'unused') RETURNING id"
                    ),
                    {"email": f"migration-second-{suffix}@example.com"},
                )
            ).scalar_one()

            shared_fingerprint = uuid.uuid4().hex * 2
            await connection.execute(
                text(
                    "INSERT INTO documents "
                    "(user_id, title, content, content_sha256) "
                    "VALUES (:user_id, 'First', 'same content', :fingerprint)"
                ),
                {"user_id": first_user_id, "fingerprint": shared_fingerprint},
            )
            await connection.execute(
                text(
                    "INSERT INTO documents "
                    "(user_id, title, content, content_sha256) "
                    "VALUES (:user_id, 'Second', 'same content', :fingerprint)"
                ),
                {"user_id": second_user_id, "fingerprint": shared_fingerprint},
            )

            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        text(
                            "INSERT INTO documents "
                            "(user_id, title, content, content_sha256) "
                            "VALUES (:user_id, 'Duplicate', 'same content', :fingerprint)"
                        ),
                        {"user_id": first_user_id, "fingerprint": shared_fingerprint},
                    )
    finally:
        if transaction is not None and transaction.is_active:
            await transaction.rollback()
        await engine.dispose()
