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

    with patch("app.services.llm.get_gemini_client", return_value=client):
        answer = await generate_answer("Каков срок хранения?", context)

    assert answer == "Ответ подтверждён. [Источник: 1]"
    client.aio.models.generate_content.assert_awaited_once()
    kwargs = client.aio.models.generate_content.await_args.kwargs
    assert kwargs["contents"].endswith(context)
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
