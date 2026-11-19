from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import generate_answer


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
async def test_generate_answer_rejects_empty_model_response():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        with pytest.raises(RuntimeError, match="empty answer"):
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
