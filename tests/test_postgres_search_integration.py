import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.search import search_document_chunks


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def postgres_session():
    if not DATABASE_URL:
        pytest.skip("PG_TEST_DATABASE_URL is not configured")

    schema = f"test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(DATABASE_URL)

    async with admin_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        DATABASE_URL,
        connect_args={
            "server_settings": {
                "search_path": f"{schema},public",
            }
        },
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    checkfirst=False,
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE INDEX ix_document_chunks_embedding_hnsw
                    ON document_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                    WHERE embedding IS NOT NULL
                    """
                )
            )

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            session.add(User(id=1, email="search@example.com", hashed_password="unused"))
            await session.commit()
            yield session
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            )
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_postgres_hybrid_search_combines_vector_and_full_text(
    postgres_session,
):
    vector_match = Document(
        user_id=1,
        title="Runtime architecture",
        content="Python service runtime",
        content_sha256="a" * 64,
    )
    text_match = Document(
        user_id=1,
        title="Operations handbook",
        content="Python service deployment guide",
        content_sha256="b" * 64,
    )
    postgres_session.add_all([vector_match, text_match])
    await postgres_session.flush()

    query_vector = [1.0] + [0.0] * 383
    orthogonal_vector = [0.0, 1.0] + [0.0] * 382
    postgres_session.add_all(
        [
            DocumentChunk(
                document_id=vector_match.id,
                chunk_index=0,
                content="Python service runtime",
                embedding=query_vector,
            ),
            DocumentChunk(
                document_id=text_match.id,
                chunk_index=0,
                content="Python service deployment guide",
                embedding=orthogonal_vector,
            ),
        ]
    )
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["Python service"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[query_vector],
        ),
    ):
        results = await search_document_chunks(
            "Python service",
            postgres_session,
            user_id=1,
            limit=5,
        )

    assert {item["document_id"] for item in results} == {
        vector_match.id,
        text_match.id,
    }
    assert results[0]["document_id"] == vector_match.id
    assert results[0]["score"] == 1.0
    assert 0 < results[1]["score"] < 1.0


@pytest.mark.asyncio
async def test_postgres_hybrid_search_filters_weak_vector_matches(
    postgres_session,
):
    # Keep the test independent if a PostgreSQL schema contains leftover rows.
    await postgres_session.execute(delete(DocumentChunk))
    await postgres_session.execute(delete(Document))
    await postgres_session.commit()

    document = Document(
        user_id=1,
        title="Unrelated material",
        content="A document without the requested terms",
        content_sha256="c" * 64,
    )
    postgres_session.add(document)
    await postgres_session.flush()
    postgres_session.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content="A document without the requested terms",
            embedding=[0.0, 1.0] + [0.0] * 382,
        )
    )
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["qzxvnonexistent"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[[1.0] + [0.0] * 383],
        ),
    ):
        results = await search_document_chunks(
            "qzxvnonexistent",
            postgres_session,
            user_id=1,
            limit=5,
        )

    assert results == []


@pytest.mark.asyncio
async def test_postgres_semantic_candidate_query_can_use_hnsw_index(
    postgres_session,
):
    query_vector = "[" + ",".join(["1"] + ["0"] * 383) + "]"
    await postgres_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = await postgres_session.execute(
        text(
            """
            EXPLAIN (COSTS OFF)
            SELECT chunk.id
            FROM document_chunks AS chunk
            JOIN documents AS document
              ON document.id = chunk.document_id
            WHERE document.user_id = :user_id
              AND chunk.embedding IS NOT NULL
              AND chunk.embedding <=> CAST(:query_vector AS vector) <= 0.55
            ORDER BY chunk.embedding <=> CAST(:query_vector AS vector)
            LIMIT 50
            """
        ),
        {"user_id": 1, "query_vector": query_vector},
    )
    plan_text = "\n".join(row[0] for row in plan.all())

    assert "ix_document_chunks_embedding_hnsw" in plan_text
