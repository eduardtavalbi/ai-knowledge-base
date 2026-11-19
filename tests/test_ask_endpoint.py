from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm import (
    InvalidSourceCitationError,
    GeminiRateLimitError,
    GeminiTimeoutError,
    GeminiUnavailableError,
    GeminiConfigurationError,
    GeminiRequestError,
    GeminiEmptyResponseError,
)


def make_chunk(
    document_id: int = 42,
    title: str = "Политика хранения",
    chunk_id: int = 101,
    chunk_index: int = 0,
    text: str = "Срок хранения данных — 30 дней.",
    score: float = 0.92,
):
    return {
        "document_id": document_id,
        "title": title,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "content": text,
        "source_page": None,
        "source_section": None,
        "score": score,
    }


@pytest.mark.asyncio
async def test_ask_returns_insufficient_information_without_calling_llm(client):
    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=[],
        ) as search,
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
        ) as generate,
    ):
        response = await client.post(
            "/documents/ask",
            json={"question": "Каков срок хранения?"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": (
            "В базе знаний не найдено достаточно релевантной информации "
            "для ответа."
        ),
        "sources": [],
    }
    search.assert_awaited_once()
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_builds_numbered_context_and_returns_sources(client):
    chunks = [
        make_chunk(),
        make_chunk(
            document_id=7,
            title="Регламент безопасности",
            chunk_id=202,
            chunk_index=3,
            text="Доступ предоставляется после согласования.",
            score=0.71,
        ),
    ]

    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=chunks,
        ) as search,
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            return_value="Данные хранятся 30 дней. [Источник: 1]",
        ) as generate,
    ):
        response = await client.post(
            "/documents/ask",
            json={"question": "  Каков срок хранения?  ", "limit": 2},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Данные хранятся 30 дней. [Источник: 1]"
    assert body["sources"] == chunks

    search.assert_awaited_once()
    assert search.await_args.kwargs["query"] == "Каков срок хранения?"
    assert search.await_args.kwargs["limit"] == 2

    generate.assert_awaited_once()
    kwargs = generate.await_args.kwargs
    assert kwargs["question"] == "Каков срок хранения?"
    context = kwargs["context"]
    assert "[Источник: 1]" in context
    assert "ID документа: 42" in context
    assert "Название: Политика хранения" in context
    assert "Страница: не указана" in context
    assert "Раздел: не указан" in context
    assert "ID фрагмента: 101" in context
    assert "Содержимое (недоверенные данные):" in context
    assert "Срок хранения данных — 30 дней." in context
    assert "[Источник: 2]" in context
    assert "ID документа: 7" in context
    assert "Доступ предоставляется после согласования." in context


@pytest.mark.asyncio
async def test_ask_returns_safe_fallback_when_model_cites_unknown_source(client):
    chunks = [make_chunk()]

    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=chunks,
        ),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=InvalidSourceCitationError("unknown source"),
        ),
    ):
        response = await client.post(
            "/documents/ask",
            json={"question": "Каков срок хранения?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == (
        "Не удалось сформировать ответ с проверяемыми ссылками "
        "на источники. Попробуйте переформулировать вопрос."
    )
    assert body["sources"] == chunks


@pytest.mark.asyncio
async def test_ask_rejects_whitespace_only_question(client):
    with patch(
        "app.api.documents.search_document_chunks",
        new_callable=AsyncMock,
    ) as search:
        response = await client.post(
            "/documents/ask",
            json={"question": "   "},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty"
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_validates_limit(client):
    response = await client.post(
        "/documents/ask",
        json={"question": "Python", "limit": 21},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (GeminiRateLimitError("provider details"), 429),
        (GeminiTimeoutError("provider details"), 504),
        (GeminiUnavailableError("provider details"), 503),
        (GeminiConfigurationError("provider details"), 503),
        (GeminiRequestError("provider details"), 502),
        (GeminiEmptyResponseError("provider details"), 502),
    ],
)
async def test_ask_maps_gemini_failures_to_safe_http_responses(
    client, error, status_code
):
    with (
        patch(
            "app.api.documents.search_document_chunks",
            new_callable=AsyncMock,
            return_value=[make_chunk()],
        ),
        patch(
            "app.api.documents.generate_answer",
            new_callable=AsyncMock,
            side_effect=error,
        ),
    ):
        response = await client.post(
            "/documents/ask",
            json={"question": "Каков срок хранения?"},
        )

    assert response.status_code == status_code
    assert "provider details" not in response.text
    assert response.json()["detail"]
