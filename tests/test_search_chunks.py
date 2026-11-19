from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import _negation_signature, search_document_chunks


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Contractors must not use VPN.", frozenset({"not"})),
        ("There is no VPN access.", frozenset({"no"})),
        ("Never share credentials.", frozenset({"never"})),
        ("Access is available without approval.", frozenset({"without"})),
        ("The system cannot connect.", frozenset({"cannot"})),
        ("The user can't connect.", frozenset({"can't"})),
        ("Сотрудникам не разрешён доступ.", frozenset({"не"})),
        ("Нет доступа к системе.", frozenset({"нет"})),
        ("Ни один подрядчик не допущен.", frozenset({"ни", "не"})),
        ("Сотрудник никогда не передаёт пароль.", frozenset({"никогда", "не"})),
        ("Доступ без согласования запрещён.", frozenset({"без"})),
    ],
)
def test_negation_signature_detects_supported_english_and_russian_markers(
    text, expected
):
    assert _negation_signature(text) == expected


def test_negation_signature_is_case_insensitive_and_ignores_substrings():
    assert _negation_signature("NOT allowed") == frozenset({"not"})
    assert _negation_signature("notebook and nobody") == frozenset()


def make_document(document_id: int, title: str = "Test"):
    return SimpleNamespace(id=document_id, title=title)


def make_chunk(
    chunk_id: int,
    document_id: int,
    content: str,
    chunk_index: int = 0,
    source_page: int | None = None,
    source_section: str | None = None,
):
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        content=content,
        chunk_index=chunk_index,
        source_page=source_page,
        source_section=source_section,
    )


def result(rows):
    value = MagicMock()
    value.all.return_value = rows
    return value


@pytest.mark.asyncio
async def test_hybrid_search_returns_relevant_chunks():
    document = make_document(1, "Python")
    chunk = make_chunk(10, 1, "FastAPI is a Python framework.", source_page=4, source_section="Backend")
    db = AsyncMock()
    db.execute.side_effect = [
        result([(document, chunk, 0.1)]),
        result([(document, chunk, 0.5)]),
    ]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["Python framework"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384) as embedding,
    ):
        chunks = await search_document_chunks("Python framework", db, limit=5)

    assert len(chunks) == 1
    assert chunks[0]["document_id"] == 1
    assert chunks[0]["chunk_id"] == 10
    assert chunks[0]["content"] == "FastAPI is a Python framework."
    assert chunks[0]["source_page"] == 4
    assert chunks[0]["source_section"] == "Backend"
    assert chunks[0]["score"] == 1.0
    embedding.assert_called_once_with("Python framework")
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_rrf_combines_rankings_from_multiple_queries():
    document = make_document(1, "Backend")
    first = make_chunk(1, 1, "Python async programming")
    second = make_chunk(2, 1, "FastAPI application framework")
    db = AsyncMock()
    db.execute.side_effect = [
        result([(document, first, 0.1), (document, second, 0.2)]),
        result([(document, second, 0.5)]),
        result([(document, second, 0.1), (document, first, 0.2)]),
        result([]),
    ]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["backend", "FastAPI async"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384),
    ):
        chunks = await search_document_chunks("backend", db, limit=5)

    assert [item["chunk_id"] for item in chunks] == [2, 1]
    assert chunks[0]["score"] == 1.0
    assert 0 < chunks[1]["score"] < 1.0
    assert db.execute.await_count == 4


@pytest.mark.asyncio
async def test_search_limits_chunks_per_document():
    document = make_document(1, "Python")
    db = AsyncMock()
    db.execute.side_effect = [
        result([
            (document, make_chunk(1, 1, "First chunk"), 0.1),
            (document, make_chunk(2, 1, "Second chunk"), 0.2),
            (document, make_chunk(3, 1, "Third chunk"), 0.3),
        ]),
        result([]),
    ]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["Python"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384),
    ):
        chunks = await search_document_chunks("Python", db, limit=5)

    assert [item["chunk_id"] for item in chunks] == [1, 2]


@pytest.mark.asyncio
async def test_search_removes_near_duplicate_chunks():
    document = make_document(1, "Python")
    db = AsyncMock()
    db.execute.side_effect = [
        result([
            (document, make_chunk(1, 1, "FastAPI is a Python framework."), 0.1),
            (document, make_chunk(2, 1, "FastAPI is a Python framework."), 0.2),
            (document, make_chunk(3, 1, "PostgreSQL stores relational data."), 0.3),
        ]),
        result([]),
    ]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["Python"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384),
    ):
        chunks = await search_document_chunks("Python", db, limit=5)

    assert [item["chunk_id"] for item in chunks] == [1, 3]


@pytest.mark.asyncio
async def test_search_filters_semantic_results_below_similarity_threshold():
    document = make_document(1)
    chunk = make_chunk(10, 1, "Unrelated content.")
    db = AsyncMock()
    db.execute.side_effect = [
        result([(document, chunk, 0.56)]),  # cosine similarity = 0.44
        result([]),  # no full-text match
    ]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["Python"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384),
    ):
        chunks = await search_document_chunks("Python", db)

    assert chunks == []


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_retrievers_match():
    db = AsyncMock()
    db.execute.side_effect = [result([]), result([])]

    with (
        patch("app.services.llm.expand_search_queries", new_callable=AsyncMock,
              return_value=["unknown topic"]),
        patch("app.services.search.generate_embedding",
              return_value=[0.1] * 384),
    ):
        chunks = await search_document_chunks("unknown topic", db)

    assert chunks == []
