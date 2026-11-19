import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.search import search_document_chunks


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="PG_TEST_DATABASE_URL is required for PostgreSQL retrieval tests",
)


@pytest_asyncio.fixture
async def postgres_session():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def embedding(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * 382


@pytest.mark.asyncio
async def test_hybrid_search_retrieves_relevant_postgres_chunks(postgres_session):
    handbook = Document(title="Remote work handbook", content="Remote work rules")
    cafeteria = Document(title="Cafeteria menu", content="Weekly meal schedule")
    postgres_session.add_all([handbook, cafeteria])
    await postgres_session.flush()

    exact_match = DocumentChunk(
        document_id=handbook.id,
        chunk_index=0,
        content="VPN access requires multi-factor authentication for remote staff.",
        embedding=embedding(1.0),
    )
    semantic_match = DocumentChunk(
        document_id=handbook.id,
        chunk_index=1,
        content="Remote login must use a second verification factor.",
        embedding=embedding(0.98, 0.2),
    )
    unrelated = DocumentChunk(
        document_id=cafeteria.id,
        chunk_index=0,
        content="The cafeteria menu is updated every Monday.",
        embedding=embedding(0.0, 1.0),
    )
    postgres_session.add_all([exact_match, semantic_match, unrelated])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access authentication"],
        ),
        patch(
            "app.services.search.generate_embedding",
            return_value=embedding(1.0),
        ),
    ):
        results = await search_document_chunks(
            "VPN access authentication",
            postgres_session,
            limit=5,
        )

    result_ids = [item["chunk_id"] for item in results]
    assert exact_match.id in result_ids
    assert semantic_match.id in result_ids
    assert unrelated.id not in result_ids
    assert result_ids.index(exact_match.id) < result_ids.index(semantic_match.id)


@pytest.mark.asyncio
async def test_postgres_search_removes_duplicates_and_limits_chunks_per_document(
    postgres_session,
):
    handbook = Document(title="VPN security handbook", content="VPN access policies")
    postgres_session.add(handbook)
    await postgres_session.flush()

    duplicate_content = (
        "VPN access requires multi-factor authentication for remote staff."
    )
    chunks = [
        DocumentChunk(
            document_id=handbook.id,
            chunk_index=0,
            content=duplicate_content,
            embedding=embedding(1.0),
        ),
        DocumentChunk(
            document_id=handbook.id,
            chunk_index=1,
            content=duplicate_content,
            embedding=embedding(0.999, 0.04),
        ),
        DocumentChunk(
            document_id=handbook.id,
            chunk_index=2,
            content=(
                "VPN access for external contractors requires approval "
                "from the security team."
            ),
            embedding=embedding(0.98, 0.2),
        ),
        DocumentChunk(
            document_id=handbook.id,
            chunk_index=3,
            content=(
                "VPN access is revoked when an employee leaves the company."
            ),
            embedding=embedding(0.95, 0.31),
        ),
    ]
    postgres_session.add_all(chunks)
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access"],
        ),
        patch(
            "app.services.search.generate_embedding",
            return_value=embedding(1.0),
        ),
    ):
        results = await search_document_chunks(
            "VPN access",
            postgres_session,
            limit=5,
        )

    result_ids = {item["chunk_id"] for item in results}
    duplicate_ids = {chunks[0].id, chunks[1].id}

    assert len(results) == 2
    assert len(result_ids & duplicate_ids) == 1
    assert any(
        item["chunk_id"] == chunks[2].id
        for item in results
    )
    assert all(item["document_id"] == handbook.id for item in results)
