from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.documents import ask_question
from app.schemas.document import AskRequest
from app.services.llm import GeminiRateLimitError, GeminiUnavailableError


@pytest.fixture
def ask_http_request():
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/documents/ask",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    })


@pytest.fixture
def ask_request():
    return AskRequest(question="Что такое Python?", limit=5)


@pytest.fixture
def chunks():
    return [{
        "title": "Python",
        "content": "Python — язык программирования.",
        "document_id": 1,
        "chunk_id": 1,
        "chunk_index": 0,
        "source_page": None,
        "source_section": None,
        "score": 0.9,
    }]


@pytest.mark.asyncio
async def test_ask_returns_429_when_gemini_quota_exhausted(ask_request, ask_http_request, chunks):
    with (
        patch("app.api.documents.enforce_rate_limit", new_callable=AsyncMock) as rate_limit,
        patch("app.api.documents.search_document_chunks", new_callable=AsyncMock, return_value=chunks),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=GeminiRateLimitError("Gemini rate limit reached"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ask_question(ask_request, ask_http_request, db=AsyncMock(), user=SimpleNamespace(id=1))

    assert exc_info.value.status_code == 429
    rate_limit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_returns_503_when_gemini_unavailable(ask_request, ask_http_request, chunks):
    with (
        patch("app.api.documents.enforce_rate_limit", new_callable=AsyncMock),
        patch("app.api.documents.search_document_chunks", new_callable=AsyncMock, return_value=chunks),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=GeminiUnavailableError("Gemini server error"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ask_question(ask_request, ask_http_request, db=AsyncMock(), user=SimpleNamespace(id=1))

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_ask_returns_answer_with_sources(ask_request, ask_http_request, chunks):
    with (
        patch("app.api.documents.enforce_rate_limit", new_callable=AsyncMock),
        patch("app.api.documents.search_document_chunks", new_callable=AsyncMock, return_value=chunks) as mock_search,
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            return_value="Python — язык программирования. [Источник: 1]",
        ) as mock_generate,
    ):
        response = await ask_question(ask_request, ask_http_request, db=AsyncMock(), user=SimpleNamespace(id=1))

    assert response.answer == "Python — язык программирования. [Источник: 1]"
    assert [source.model_dump() for source in response.sources] == chunks
    mock_search.assert_awaited_once()
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_returns_message_when_no_chunks_found(ask_request, ask_http_request):
    with (
        patch("app.api.documents.enforce_rate_limit", new_callable=AsyncMock),
        patch("app.api.documents.search_document_chunks", new_callable=AsyncMock, return_value=[]),
        patch("app.api.documents.generate_answer", new_callable=AsyncMock) as mock_generate,
    ):
        response = await ask_question(ask_request, ask_http_request, db=AsyncMock(), user=SimpleNamespace(id=1))

    assert "не найдено" in response.answer
    assert response.sources == []
    mock_generate.assert_not_awaited()
