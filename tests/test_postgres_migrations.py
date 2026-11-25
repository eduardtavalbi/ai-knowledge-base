import asyncio
import os
import threading
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.documents import _create_document_if_new
from app.models.document import Document
from app.models.user import User


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


@pytest.mark.asyncio
async def test_concurrent_document_creation_returns_the_same_existing_record():
    if not DATABASE_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not configured")

    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    content = f"Concurrent document creation {suffix}"
    user_id = None

    try:
        async with session_factory() as session:
            user = User(
                email=f"concurrent-{suffix}@example.com",
                hashed_password="unused",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        # Force both requests past the initial duplicate lookup before either
        # can insert, reproducing the unique-constraint race deterministically.
        embedding_barrier = threading.Barrier(2)

        def generate_test_embedding(_content: str) -> list[float]:
            embedding_barrier.wait(timeout=10)
            return [0.0] * 384

        async def create_document():
            async with session_factory() as session:
                return await _create_document_if_new(
                    title="Concurrent upload",
                    content=content,
                    db=session,
                    user_id=user_id,
                )

        with (
            patch(
                "app.api.documents.generate_embedding",
                side_effect=generate_test_embedding,
            ),
            patch(
                "app.api.documents.save_document_chunks",
                new_callable=AsyncMock,
            ),
        ):
            results = await asyncio.gather(
                create_document(),
                create_document(),
            )

        documents, created_flags = zip(*results, strict=True)
        assert documents[0].id == documents[1].id
        assert sorted(created_flags) == [False, True]
    finally:
        if user_id is not None:
            async with session_factory() as session:
                await session.execute(
                    delete(Document).where(Document.user_id == user_id)
                )
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        await engine.dispose()
