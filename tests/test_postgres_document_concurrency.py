import asyncio
import hashlib
import os
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.documents import update_document
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentUpdate


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_concurrent_updates_cannot_create_duplicate_content_for_one_user():
    if not DATABASE_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not configured")

    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    user_id = None

    try:
        async with session_factory() as session:
            user = User(
                email=f"concurrent-update-{suffix}@example.com",
                hashed_password="unused",
            )
            session.add(user)
            await session.flush()
            user_id = user.id

            first = Document(
                user_id=user_id,
                title="First original",
                content="First original content",
                content_sha256=hashlib.sha256(
                    f"first-{suffix}".encode()
                ).hexdigest(),
                embedding=[0.0] * 384,
            )
            second = Document(
                user_id=user_id,
                title="Second original",
                content="Second original content",
                content_sha256=hashlib.sha256(
                    f"second-{suffix}".encode()
                ).hexdigest(),
                embedding=[0.0] * 384,
            )
            session.add_all([first, second])
            await session.commit()
            document_ids = (first.id, second.id)

        # Both updates must finish their duplicate lookup before either one
        # writes the shared fingerprint. This deterministically exercises the
        # PostgreSQL unique constraint rather than relying on scheduler timing.
        embedding_barrier = threading.Barrier(2)
        shared_content = f"Shared concurrent update content {suffix}"

        def generate_test_embedding(_content: str) -> list[float]:
            embedding_barrier.wait(timeout=10)
            return [0.0] * 384

        async def update_one(document_id: int, title: str):
            async with session_factory() as session:
                try:
                    return await update_document(
                        document_id=document_id,
                        document_data=DocumentUpdate(
                            title=title,
                            content=shared_content,
                        ),
                        db=session,
                        user=SimpleNamespace(id=user_id),
                    )
                except HTTPException as exc:
                    return exc

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
                update_one(document_ids[0], "First updated"),
                update_one(document_ids[1], "Second updated"),
            )

        successes = [result for result in results if isinstance(result, Document)]
        conflicts = [
            result
            for result in results
            if isinstance(result, HTTPException)
        ]

        assert len(successes) == 1
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].detail == (
            "Another document already has identical content"
        )

        async with session_factory() as session:
            documents = (
                await session.execute(
                    select(Document)
                    .where(Document.id.in_(document_ids))
                    .order_by(Document.id)
                )
            ).scalars().all()

        assert len(documents) == 2
        assert sum(document.content == shared_content for document in documents) == 1
        assert sum(
            document.content in {
                "First original content",
                "Second original content",
            }
            for document in documents
        ) == 1
    finally:
        if user_id is not None:
            async with session_factory() as session:
                await session.execute(
                    delete(Document).where(Document.user_id == user_id)
                )
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        await engine.dispose()
