import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.search import search_document_chunks


DATABASE_URL = os.getenv("PG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="PG_TEST_DATABASE_URL is required for PostgreSQL retrieval tests",
)


@pytest_asyncio.fixture
async def postgres_session():
    schema = f"retrieval_{uuid.uuid4().hex}"
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
            # checkfirst=False is required: public tables are visible through the
            # search_path, but this fixture must create its own schema tables.
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    checkfirst=False,
                )
            )

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            session.add(User(id=1, email="retrieval@example.com", hashed_password="unused"))
            await session.commit()
            yield session
            await session.rollback()
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            )
        await admin_engine.dispose()


def embedding(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * 382


@pytest.mark.asyncio
async def test_hybrid_search_retrieves_relevant_postgres_chunks(postgres_session):
    handbook = Document(user_id=1, title="Remote work handbook", content="Remote work rules")
    cafeteria = Document(user_id=1, title="Cafeteria menu", content="Weekly meal schedule")
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
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            "VPN access authentication",
            postgres_session,
            user_id=1,
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
    handbook = Document(user_id=1, title="VPN security handbook", content="VPN access policies")
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
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            "VPN access",
            postgres_session,
            user_id=1,
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


@pytest.mark.asyncio
async def test_postgres_search_supports_russian_and_english_expansions(
    postgres_session,
):
    russian_doc = Document(
        user_id=1,
        title="Политика удалённой работы",
        content="Правила работы сотрудников из дома",
    )
    english_doc = Document(
        user_id=1,
        title="Remote work policy",
        content="Rules for employees working from home",
    )
    postgres_session.add_all([russian_doc, english_doc])
    await postgres_session.flush()

    russian_chunk = DocumentChunk(
        document_id=russian_doc.id,
        chunk_index=0,
        content="Сотрудникам разрешена удалённая работа по согласованию.",
        embedding=embedding(1.0),
    )
    english_chunk = DocumentChunk(
        document_id=english_doc.id,
        chunk_index=0,
        content="Employees may work remotely with manager approval.",
        embedding=embedding(0.0, 1.0),
    )
    postgres_session.add_all([russian_chunk, english_chunk])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["удалённая работа", "remote work"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0), embedding(1.0), embedding(0.0, 1.0)],
        ),
    ):
        results = await search_document_chunks(
            "работа из дома",
            postgres_session,
            user_id=1,
            limit=5,
        )

    result_ids = {item["chunk_id"] for item in results}
    assert russian_chunk.id in result_ids
    assert english_chunk.id in result_ids
    assert len(results) == 2


@pytest.mark.asyncio
async def test_postgres_search_keeps_conflicting_policy_sources(postgres_session):
    old_policy = Document(
        user_id=1,
        title="VPN policy 2024",
        content="External contractors do not need VPN access.",
    )
    current_policy = Document(
        user_id=1,
        title="VPN policy 2026",
        content="External contractors must use VPN access.",
    )
    postgres_session.add_all([old_policy, current_policy])
    await postgres_session.flush()

    old_chunk = DocumentChunk(
        document_id=old_policy.id,
        chunk_index=0,
        content="External contractors do not need VPN access.",
        embedding=embedding(1.0),
    )
    current_chunk = DocumentChunk(
        document_id=current_policy.id,
        chunk_index=0,
        content="External contractors must use VPN access.",
        embedding=embedding(0.98, 0.2),
    )
    postgres_session.add_all([old_chunk, current_chunk])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access contractors"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            "VPN access contractors",
            postgres_session,
            user_id=1,
            limit=5,
        )

    result_ids = {item["chunk_id"] for item in results}
    assert old_chunk.id in result_ids
    assert current_chunk.id in result_ids
    assert len(results) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "positive_text", "negative_text", "query"),
    [
        (
            "Contractor VPN policy",
            "Contractors must use VPN access.",
            "Contractors must not use VPN access.",
            "contractors VPN access",
        ),
        (
            "Политика VPN для подрядчиков",
            "Подрядчики должны использовать VPN.",
            "Подрядчики не должны использовать VPN.",
            "подрядчики VPN",
        ),
    ],
)
async def test_postgres_search_preserves_near_identical_chunks_with_opposite_negation(
    postgres_session,
    title,
    positive_text,
    negative_text,
    query,
):
    policy = Document(
        user_id=1,
        title=title,
        content=f"{positive_text} {negative_text}",
    )
    postgres_session.add(policy)
    await postgres_session.flush()

    allowed = DocumentChunk(
        document_id=policy.id,
        chunk_index=0,
        content=positive_text,
        embedding=embedding(1.0),
    )
    prohibited = DocumentChunk(
        document_id=policy.id,
        chunk_index=1,
        content=negative_text,
        embedding=embedding(0.999, 0.04),
    )
    postgres_session.add_all([allowed, prohibited])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=[query],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            query,
            postgres_session,
            user_id=1,
            limit=5,
        )

    result_ids = {item["chunk_id"] for item in results}
    assert allowed.id in result_ids
    assert prohibited.id in result_ids
    assert len(results) == 2



@pytest.mark.asyncio
async def test_postgres_search_keeps_identical_chunks_from_separate_documents(
    postgres_session,
):
    first_doc = Document(
        user_id=1,
        title="Security handbook",
        content="VPN access requires multi-factor authentication.",
    )
    second_doc = Document(
        user_id=1,
        title="Remote access policy",
        content="VPN access requires multi-factor authentication.",
    )
    postgres_session.add_all([first_doc, second_doc])
    await postgres_session.flush()

    first_chunk = DocumentChunk(
        document_id=first_doc.id,
        chunk_index=0,
        content="VPN access requires multi-factor authentication.",
        embedding=embedding(1.0),
    )
    second_chunk = DocumentChunk(
        document_id=second_doc.id,
        chunk_index=0,
        content="VPN access requires multi-factor authentication.",
        embedding=embedding(0.999, 0.04),
    )
    postgres_session.add_all([first_chunk, second_chunk])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access authentication"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            "VPN access authentication",
            postgres_session,
            user_id=1,
            limit=5,
        )

    result_ids = {item["chunk_id"] for item in results}
    result_document_ids = {item["document_id"] for item in results}

    assert result_ids == {first_chunk.id, second_chunk.id}
    assert result_document_ids == {first_doc.id, second_doc.id}
    assert len(results) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "content", "query"),
    [
        (
            "Russian employee handbook",
            "Сотрудники получают доступ к корпоративной системе.",
            "сотрудник",
        ),
        (
            "English employee handbook",
            "Employees receive access to the corporate system.",
            "employee",
        ),
    ],
)
async def test_postgres_full_text_search_matches_inflected_words(
    postgres_session,
    title,
    content,
    query,
):
    document = Document(user_id=1, title=title, content=content)
    postgres_session.add(document)
    await postgres_session.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content=content,
        # Deliberately orthogonal to the query embedding: this test must pass
        # through PostgreSQL full-text search, not semantic retrieval.
        embedding=embedding(0.0, 1.0),
    )
    postgres_session.add(chunk)
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0, 0.0)],
        ),
    ):
        results = await search_document_chunks(
            query,
            postgres_session,
            user_id=1,
            limit=5,
        )

    assert [item["chunk_id"] for item in results] == [chunk.id]


@pytest.mark.asyncio
async def test_postgres_retrieval_never_returns_another_users_chunks(postgres_session):
    other_user = User(
        id=2,
        email="other-retrieval@example.com",
        hashed_password="unused",
    )
    postgres_session.add(other_user)
    await postgres_session.flush()

    own_document = Document(
        user_id=1,
        title="Private account one",
        content="Confidential architecture notes",
    )
    other_document = Document(
        user_id=2,
        title="Private account two",
        content="Confidential architecture notes",
    )
    postgres_session.add_all([own_document, other_document])
    await postgres_session.flush()

    own_chunk = DocumentChunk(
        document_id=own_document.id,
        chunk_index=0,
        content="Confidential architecture notes for account one.",
        embedding=embedding(1.0),
    )
    other_chunk = DocumentChunk(
        document_id=other_document.id,
        chunk_index=0,
        content="Confidential architecture notes for account two.",
        embedding=embedding(1.0),
    )
    postgres_session.add_all([own_chunk, other_chunk])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        results = await search_document_chunks(
            "Confidential architecture notes",
            postgres_session,
            user_id=1,
            limit=5,
        )

    assert [item["chunk_id"] for item in results] == [own_chunk.id]
    assert all(item["document_id"] == own_document.id for item in results)

@pytest.mark.asyncio
async def test_currentness_query_prefers_active_policy_but_keeps_historical_search(
    postgres_session,
):
    superseded = Document(
        user_id=1,
        title="Annual Leave Policy 2024 (superseded)",
        content=(
            "Annual leave policy grants employees twenty days of paid leave. "
            "This policy is superseded by the 2026 policy."
        ),
    )
    current = Document(
        user_id=1,
        title="Annual Leave Policy 2026",
        content="Annual leave policy grants employees twenty days of paid leave.",
    )
    postgres_session.add_all([superseded, current])
    await postgres_session.flush()

    superseded_chunk = DocumentChunk(
        document_id=superseded.id,
        chunk_index=0,
        content="Annual leave policy grants employees twenty days of paid leave.",
        embedding=embedding(1.0),
    )
    current_chunk = DocumentChunk(
        document_id=current.id,
        chunk_index=0,
        content="Annual leave policy grants employees twenty days of paid leave.",
        embedding=embedding(0.999, 0.04),
    )
    postgres_session.add_all([superseded_chunk, current_chunk])
    await postgres_session.commit()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[embedding(1.0)],
        ),
    ):
        current_results = [
            await search_document_chunks(
                current_query,
                postgres_session,
                user_id=1,
                limit=5,
            )
            for current_query in (
                "What is the current annual leave policy?",
                "Какая актуальная политика отпусков?",
            )
        ]
        historical_results = await search_document_chunks(
            "What did the 2024 annual leave policy say?",
            postgres_session,
            user_id=1,
            limit=5,
        )

    for results in current_results:
        assert results[0]["document_id"] == current.id
        assert superseded.id in {item["document_id"] for item in results}
    assert historical_results[0]["document_id"] == superseded.id
