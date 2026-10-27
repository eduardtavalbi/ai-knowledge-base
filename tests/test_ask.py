
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from google.genai.errors import ClientError, ServerError

from app.api.documents import ask_question
from app.schemas.document import AskRequest


@pytest.fixture
def ask_request():
    return AskRequest(question="Что такое Python?", limit=5)


@pytest.mark.asyncio
async def test_ask_returns_429_when_gemini_quota_exhausted(ask_request):
    chunks = [
        {
            "title": "Python",
            "content": "Python — язык программирования.",
            "document_id": 1,
            "chunk_id": 1,
            "chunk_index": 0,
            "score": 0.9,
        }
    ]

    error = ClientError(
        429,
        {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}},
    )

    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=chunks,
        ),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=error,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ask_question(ask_request, db=AsyncMock())

    assert exc_info.value.status_code == 429
    assert "лимит запросов Gemini API" in exc_info.value.detail


@pytest.mark.asyncio
async def test_ask_returns_503_when_gemini_unavailable(ask_request):
    chunks = [
        {
            "title": "Python",
            "content": "Python — язык программирования.",
            "document_id": 1,
            "chunk_id": 1,
            "chunk_index": 0,
            "score": 0.9,
        }
    ]

    error = ServerError(
        503,
        {"error": {"message": "Unavailable", "status": "UNAVAILABLE"}},
    )

    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=chunks,
        ),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=error,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ask_question(ask_request, db=AsyncMock())

    assert exc_info.value.status_code == 503

@pytest.mark.asyncio
async def test_ask_returns_answer_with_sources(ask_request):
    chunks = [
        {
            "title": "Python",
            "content": "Python — язык программирования.",
            "document_id": 1,
            "chunk_id": 1,
            "chunk_index": 0,
            "score": 0.9,
        }
    ]

    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=chunks,
        ) as mock_search,
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            return_value="Python — язык программирования.",
        ) as mock_generate,
    ):
        response = await ask_question(ask_request, db=AsyncMock())

    assert response.answer == "Python — язык программирования."
    assert [source.model_dump() for source in response.sources] == chunks
    mock_search.assert_awaited_once()
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_returns_message_when_no_chunks_found(ask_request):
    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
        ) as mock_generate,
    ):
        response = await ask_question(ask_request, db=AsyncMock())

    assert "не найдено" in response.answer
    assert response.sources == []
    mock_generate.assert_not_awaited()