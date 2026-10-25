
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import search_documents


def make_document(document_id: int, title: str = "Test") -> SimpleNamespace:
    return SimpleNamespace(
        id=document_id,
        title=title,
        content=f"Content of {title}",
    )


@pytest.mark.asyncio
async def test_search_documents_returns_unique_documents():
    first = make_document(1, "First")
    second = make_document(2, "Second")

    result = MagicMock()
    result.all.return_value = [
        (first, 0.1, 0),
        (first, 0.2, 0),
        (second, 0.3, 0),
    ]

    title_result = MagicMock()
    title_result.scalars.return_value.all.return_value = []

    semantic_result = MagicMock()
    semantic_result.all.return_value = [
        (first, 0.1),
        (first, 0.2),
        (second, 0.3),
    ]

    db = AsyncMock()
    text_result = MagicMock()
    text_result.all.return_value = []

    db.execute.side_effect = [
        title_result,
        text_result,
        semantic_result,
    ]

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ) as mock_embedding:
        documents = await search_documents(
            query="Python",
            db=db,
            limit=5,
        )

    assert [item["id"] for item in documents] == [1, 2]
    assert documents[0]["score"] == 0.9
    assert documents[1]["score"] == 0.7
    assert documents[0]["content"] == "Content of First"

    mock_embedding.assert_called_once_with("Python")
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_search_documents_filters_low_scores():
    accepted = make_document(1, "Accepted")
    rejected = make_document(2, "Rejected")

    result = MagicMock()
    result.all.return_value = [
        (accepted, 0.55, 0),
        (rejected, 0.56, 0),
    ]

    title_result = MagicMock()
    title_result.scalars.return_value.all.return_value = []

    semantic_result = MagicMock()
    semantic_result.all.return_value = [
        (accepted, 0.55),
        (rejected, 0.56),
    ]

    db = AsyncMock()
    text_result = MagicMock()
    text_result.all.return_value = []

    db.execute.side_effect = [
        title_result,
        text_result,
        semantic_result,
    ]

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        documents = await search_documents(
            query="Python",
            db=db,
        )

    assert len(documents) == 1
    assert documents[0]["id"] == 1
    assert documents[0]["score"] == 0.45


@pytest.mark.asyncio
async def test_search_documents_returns_empty_list():
    result = MagicMock()
    result.all.return_value = []

    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.search.generate_embedding",
        return_value=[0.1] * 384,
    ):
        documents = await search_documents(
            query="Unknown topic",
            db=db,
        )

    assert documents == []
