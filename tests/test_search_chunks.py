
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import search_document_chunks


def make_document(document_id: int, title: str = "Test"):
    return SimpleNamespace(id=document_id, title=title)


def make_chunk(
    chunk_id: int,
    document_id: int,
    content: str,
    chunk_index: int = 0,
):
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        content=content,
        chunk_index=chunk_index,
    )


@pytest.mark.asyncio
async def test_search_document_chunks_returns_relevant_chunks():
    document = make_document(1, "Python")
    chunk = make_chunk(10, 1, "FastAPI is a Python framework.")

    result = MagicMock()
    result.all.return_value = [(document, chunk, 0.1)]

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ) as mock_embedding:
        chunks = await search_document_chunks(
            query="Python framework",
            db=db,
            limit=5,
        )

    assert len(chunks) == 1
    assert chunks[0]["document_id"] == 1
    assert chunks[0]["title"] == "Python"
    assert chunks[0]["chunk_id"] == 10
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"] == "FastAPI is a Python framework."
    assert chunks[0]["score"] == 0.9

    mock_embedding.assert_called_once_with("Python framework")
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_document_chunks_filters_low_scores():
    document = make_document(1)
    chunk = make_chunk(10, 1, "Unrelated content.")

    result = MagicMock()
    result.all.return_value = [(document, chunk, 0.56)]

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        chunks = await search_document_chunks(
            query="Python",
            db=db,
        )

    assert chunks == []


@pytest.mark.asyncio
async def test_search_document_chunks_returns_empty_list():
    result = MagicMock()
    result.all.return_value = []

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        chunks = await search_document_chunks(
            query="Unknown topic",
            db=db,
        )

    assert chunks == []



@pytest.mark.asyncio
async def test_search_document_chunks_limits_chunks_per_document():
    document = make_document(1, "Python")

    result = MagicMock()
    result.all.return_value = [
        (document, make_chunk(1, 1, "First chunk"), 0.1),
        (document, make_chunk(2, 1, "Second chunk"), 0.2),
        (document, make_chunk(3, 1, "Third chunk"), 0.3),
    ]

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        chunks = await search_document_chunks(
            query="Python",
            db=db,
            limit=5,
        )

    assert len(chunks) == 2
    assert [item["chunk_id"] for item in chunks] == [1, 2]


@pytest.mark.asyncio
async def test_search_document_chunks_removes_near_duplicates():
    document = make_document(1, "Python")

    result = MagicMock()
    result.all.return_value = [
        (
            document,
            make_chunk(1, 1, "FastAPI is a Python framework."),
            0.1,
        ),
        (
            document,
            make_chunk(2, 1, "FastAPI is a Python framework."),
            0.2,
        ),
        (
            document,
            make_chunk(3, 1, "PostgreSQL stores relational data."),
            0.3,
        ),
    ]

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        chunks = await search_document_chunks(
            query="Python",
            db=db,
            limit=5,
        )

    assert [item["chunk_id"] for item in chunks] == [1, 3]
