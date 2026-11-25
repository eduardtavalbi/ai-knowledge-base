from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import (
    _multilingual_fts_expressions,
    _negation_signature,
    _prepare_search_queries,
    search_document_chunks,
)


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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]) as embedding,
    ):
        chunks = await search_document_chunks("Python framework", db, limit=5)

    assert len(chunks) == 1
    assert chunks[0]["document_id"] == 1
    assert chunks[0]["chunk_id"] == 10
    assert chunks[0]["content"] == "FastAPI is a Python framework."
    assert chunks[0]["source_page"] == 4
    assert chunks[0]["source_section"] == "Backend"
    assert chunks[0]["score"] == 1.0
    embedding.assert_called_once_with(["Python framework"])
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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
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
        patch("app.services.search.generate_embeddings",
              side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
    ):
        chunks = await search_document_chunks("unknown topic", db)

    assert chunks == []



def test_prepare_search_queries_always_keeps_original_and_removes_duplicates():
    queries = _prepare_search_queries(
        "Original question",
        [
            "Alternative formulation",
            "original question",
            "Alternative formulation!",
            "x" * 201,
            "Another useful formulation",
        ],
        max_queries=3,
    )

    assert queries == ["Original question", "Alternative formulation", "Another useful formulation"]


@pytest.mark.asyncio
async def test_search_uses_original_query_even_when_expansion_omits_it():
    document = make_document(1, "VPN policy")
    original_chunk = make_chunk(1, 1, "Original query finds this policy.")
    alternative_chunk = make_chunk(2, 1, "Alternative wording finds this policy.")
    db = AsyncMock()
    db.execute.side_effect = [
        result([(document, original_chunk, 0.1)]),
        result([]),
        result([(document, alternative_chunk, 0.1)]),
        result([]),
    ]

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["alternative wording"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            side_effect=lambda texts: [[0.1] * 384 for _ in texts],
        ) as embedding,
    ):
        chunks = await search_document_chunks("original question", db, limit=5)

    embedding.assert_called_once_with([
        "original question",
        "alternative wording",
    ])
    assert {chunk["chunk_id"] for chunk in chunks} == {1, 2}
    assert db.execute.await_count == 4



@pytest.mark.asyncio
async def test_search_rejects_incomplete_batched_embeddings_before_database_queries():
    db = AsyncMock()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["first alternative", "second alternative"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            return_value=[[0.1] * 384, [0.2] * 384],
        ) as embedding,
    ):
        with pytest.raises(
            RuntimeError,
            match="Embedding count does not match search query count",
        ):
            await search_document_chunks("original query", db, limit=5)

    embedding.assert_called_once_with(
        ["original query", "first alternative", "second alternative"]
    )
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_skips_expansion_and_embeddings_for_blank_query():
    db = AsyncMock()

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
        ) as expansion,
        patch(
            "app.services.search.generate_embeddings",
        ) as embedding,
    ):
        chunks = await search_document_chunks("   ", db, limit=5)

    assert chunks == []
    expansion.assert_not_awaited()
    embedding.assert_not_called()
    db.execute.assert_not_awaited()

@pytest.mark.asyncio
async def test_search_preserves_conflicting_chunks_with_and_without_negation():
    document = make_document(1, "VPN policy")
    affirmative = make_chunk(
        1, 1, "External contractors must use VPN access."
    )
    negative = make_chunk(
        2, 1, "External contractors must not use VPN access."
    )
    db = AsyncMock()
    db.execute.side_effect = [
        result([
            (document, affirmative, 0.1),
            (document, negative, 0.11),
        ]),
        result([]),
    ]

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            side_effect=lambda texts: [[0.1] * 384 for _ in texts],
        ),
    ):
        chunks = await search_document_chunks("VPN access", db, limit=5)

    assert [chunk["chunk_id"] for chunk in chunks] == [1, 2]
    assert "must use" in chunks[0]["content"]
    assert "must not use" in chunks[1]["content"]


@pytest.mark.asyncio
async def test_search_preserves_identical_chunks_from_different_documents():
    first_document = make_document(1, "VPN policy — department A")
    second_document = make_document(2, "VPN policy — department B")
    shared_text = "External contractors must use VPN access."
    db = AsyncMock()
    db.execute.side_effect = [
        result([
            (first_document, make_chunk(1, 1, shared_text), 0.1),
            (second_document, make_chunk(2, 2, shared_text), 0.11),
        ]),
        result([]),
    ]

    with (
        patch(
            "app.services.llm.expand_search_queries",
            new_callable=AsyncMock,
            return_value=["VPN access"],
        ),
        patch(
            "app.services.search.generate_embeddings",
            side_effect=lambda texts: [[0.1] * 384 for _ in texts],
        ),
    ):
        chunks = await search_document_chunks("VPN access", db, limit=5)

    assert [chunk["document_id"] for chunk in chunks] == [1, 2]
    assert [chunk["chunk_id"] for chunk in chunks] == [1, 2]

def test_multilingual_fts_uses_russian_and_english_dictionaries():
    from sqlalchemy import literal
    from sqlalchemy.dialects import postgresql

    vector, query = _multilingual_fts_expressions(
        literal("VPN политика access policy"),
        "доступ access",
    )

    compiled_vector = vector.compile(dialect=postgresql.dialect())
    compiled_query = query.compile(dialect=postgresql.dialect())

    vector_configs = set(compiled_vector.params.values())
    query_configs = set(compiled_query.params.values())

    assert {"russian", "english"} <= vector_configs
    assert {"russian", "english"} <= query_configs
    assert "to_tsvector" in str(compiled_vector)
    assert "plainto_tsquery" in str(compiled_query)
