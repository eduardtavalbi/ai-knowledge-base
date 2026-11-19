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
