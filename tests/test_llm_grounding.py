from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import (
    generate_answer,
    expand_search_queries,
    GeminiEmptyResponseError,
    GeminiTimeoutError,
    GeminiUnavailableError,
)


@pytest.mark.asyncio
async def test_generate_answer_uses_only_context_and_requires_source_citations():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Ответ подтверждён. [Источник: 1]")
    )

    context = (
        "[Источник: 1]\n"
        "Название: Регламент\n"
        "Содержимое (недоверенные данные):\n"
        "Срок хранения — 30 дней."
    )
    question = "Каков срок хранения?"

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer(question, context)

    assert answer == "Ответ подтверждён. [Источник: 1]"
    client.aio.models.generate_content.assert_awaited_once()
    kwargs = client.aio.models.generate_content.await_args.kwargs
    assert f"Контекст:\n{context}" in kwargs["contents"]
    assert f"Вопрос:\n{question}" in kwargs["contents"]
    instruction = kwargs["config"].system_instruction
    assert "единственный источник фактов" in instruction
    assert "недоверенные данные" in instruction
    assert "[Источник: N]" in instruction
    assert "Не выдумывай источники" in instruction



@pytest.mark.asyncio
async def test_generate_answer_rejects_answer_without_source_citations():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Срок хранения составляет 30 дней.")
    )
    context = "[Источник: 1]\nСрок хранения — 30 дней."

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(ValueError, match="without source citations"):
            await generate_answer("Вопрос", context)


@pytest.mark.asyncio
async def test_generate_answer_rejects_malformed_source_citation():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Ответ. [Источник: неизвестно]")
    )
    context = "[Источник: 1]\nПроверенный факт."

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(ValueError, match="invalid source citation"):
            await generate_answer("Вопрос", context)


@pytest.mark.asyncio
async def test_generate_answer_rejects_empty_model_response():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(GeminiEmptyResponseError, match="empty answer"):
            await generate_answer("Вопрос", "[Источник: 1] Данные")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(),
        type(
            "BlockedResponse",
            (),
            {"text": property(lambda self: (_ for _ in ()).throw(ValueError("no text candidate")))},
        )(),
    ],
)
async def test_generate_answer_handles_response_without_readable_text(response):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(GeminiEmptyResponseError):
            await generate_answer("Вопрос", "[Источник: 1] Данные")


@pytest.mark.asyncio
async def test_generate_answer_rejects_citation_to_unknown_source():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Ответ. [Источник: 2]")
    )
    context = "[Источник: 1]\nСодержимое: проверенный факт."

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(ValueError, match="unknown source citation"):
            await generate_answer("Вопрос", context)


@pytest.mark.asyncio
async def test_generate_answer_accepts_citations_present_in_context():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text="Первый факт [Источник: 1]. Второй факт [Источник: 2]."
        )
    )
    context = (
        "[Источник: 1]\nПервый фрагмент.\n\n"
        "[Источник: 2]\nВторой фрагмент."
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer("Вопрос", context)

    assert "[Источник: 1]" in answer
    assert "[Источник: 2]" in answer


@pytest.mark.asyncio
async def test_generate_answer_normalizes_timeout_errors():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        side_effect=TimeoutError("sensitive provider details")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(GeminiTimeoutError):
            await generate_answer("Вопрос", "[Источник: 1] Данные")


@pytest.mark.asyncio
async def test_generate_answer_normalizes_network_errors():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        side_effect=OSError("connection details")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(GeminiUnavailableError):
            await generate_answer("Вопрос", "[Источник: 1] Данные")



@pytest.mark.asyncio
async def test_expand_search_queries_falls_back_when_gemini_is_unavailable():
    with patch(
        "app.services.llm.get_gemini_client",
        side_effect=GeminiUnavailableError("provider unavailable"),
    ):
        queries = await expand_search_queries("Как настроить доступ?", max_queries=3)

    assert queries == ["Как настроить доступ?"]


@pytest.mark.asyncio
async def test_expand_search_queries_ignores_empty_model_response():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="  \n")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("Политика отпусков", max_queries=3)

    assert queries == ["Политика отпусков"]


@pytest.mark.asyncio
async def test_expand_search_queries_deduplicates_and_respects_limit():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                "- Политика отпусков\n"
                "- правила предоставления отпуска\n"
                "- Как оформить отпуск сотруднику"
            )
        )
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("Политика отпусков", max_queries=2)

    assert queries[0] == "Политика отпусков"
    assert len(queries) == 2
    assert queries[1] == "правила предоставления отпуска"
