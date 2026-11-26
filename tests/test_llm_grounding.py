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
async def test_expand_search_queries_requests_an_opposite_language_variant():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                "Can contractors use an employee VPN profile?\n"
                "Как подрядчикам получить удалённый доступ?"
            )
        )
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries(
            "Может ли подрядчик использовать VPN-профиль сотрудника?",
            max_queries=3,
        )

    assert queries[0] == "Может ли подрядчик использовать VPN-профиль сотрудника?"
    assert "Can contractors use an employee VPN profile?" in queries
    prompt = client.aio.models.generate_content.await_args.kwargs["contents"]
    assert "с русского на английский" in prompt
    assert "с английского на русский" in prompt
    instruction = (
        client.aio.models.generate_content.await_args.kwargs[
            "config"
        ].system_instruction
    )
    assert "Сохраняй сущности, ограничения и отрицания" in instruction

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


@pytest.mark.asyncio
async def test_expand_search_queries_ignores_overlong_generated_candidates():
    client = MagicMock()
    long_candidate = "политика " * 30
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=f"{long_candidate}\n- правила оформления отпуска"
        )
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("Отпуск", max_queries=3)

    assert queries == ["Отпуск", "правила оформления отпуска"]


@pytest.mark.asyncio
async def test_expand_search_queries_falls_back_when_response_has_no_text():
    class BlockedResponse:
        @property
        def text(self):
            raise ValueError("no text candidate")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=BlockedResponse()
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("Настройка доступа", max_queries=3)

    assert queries == ["Настройка доступа"]


@pytest.mark.asyncio
async def test_generate_answer_allows_explicit_abstention_without_irrelevant_citation():
    abstention = (
        "В базе знаний нет достаточной информации, чтобы ответить на этот вопрос."
    )
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=abstention)
    )
    context = (
        "[Источник: 1]\n"
        "Название: Меню столовой\n"
        "Содержимое (недоверенные данные): блюда на этой неделе."
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer("Какой срок хранения паролей?", context)

    assert answer == abstention
    instruction = (
        client.aio.models.generate_content.await_args.kwargs[
            "config"
        ].system_instruction
    )
    assert "по-русски" in instruction
    assert "по-английски" in instruction
    assert "Не добавляй ссылку на нерелевантный источник" in instruction


@pytest.mark.asyncio
async def test_generate_answer_allows_english_abstention_without_irrelevant_citation():
    abstention = (
        "The knowledge base does not contain enough information to answer the question."
    )
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=abstention)
    )
    context = (
        "[Источник: 1]\n"
        "Title: Cafeteria menu\n"
        "Untrusted content: meals served this week."
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer("What is the password retention period?", context)

    assert answer == abstention


@pytest.mark.asyncio
async def test_generate_answer_does_not_allow_uncited_claim_after_abstention():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text=(
                "В базе знаний нет достаточной информации. "
                "Срок хранения паролей — 90 дней."
            )
        )
    )
    context = "[Источник: 1]\nНерелевантный документ."

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(ValueError, match="without source citations"):
            await generate_answer("Какой срок хранения паролей?", context)


@pytest.mark.asyncio
async def test_generate_answer_explains_conflicting_sources_and_cites_both():
    answer_text = (
        "В документах есть противоречие: политика 2024 года разрешает "
        "доступ без VPN [Источник: 1], а политика 2026 года требует VPN "
        "[Источник: 2]. По этим данным нельзя однозначно определить "
        "действующее правило без уточнения актуальности документов."
    )
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=answer_text)
    )
    context = (
        "[Источник: 1]\n"
        "Название: VPN policy 2024\n"
        "Содержимое (недоверенные данные): подрядчикам VPN не нужен.\n\n"
        "[Источник: 2]\n"
        "Название: VPN policy 2026\n"
        "Содержимое (недоверенные данные): подрядчики обязаны использовать VPN."
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer(
            "Нужен ли подрядчикам VPN?",
            context,
        )

    assert answer == answer_text
    assert "[Источник: 1]" in answer
    assert "[Источник: 2]" in answer
    instruction = (
        client.aio.models.generate_content.await_args.kwargs[
            "config"
        ].system_instruction
    )
    assert "Если источники противоречат друг другу" in instruction
    assert "не выбирай произвольно одну версию" in instruction
