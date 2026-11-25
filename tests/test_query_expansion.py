from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import expand_search_queries


@pytest.mark.asyncio
async def test_expand_search_queries_keeps_original_and_deduplicates():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text="- Python asynchronous programming\n"
                 "- Python async programming\n"
                 "3. FastAPI concurrency"
        )
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("Python async programming")

    assert queries == [
        "Python async programming",
        "FastAPI concurrency",
    ]
    client.aio.models.generate_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_expand_search_queries_falls_back_when_gemini_fails():
    with patch(
        "app.services.llm.get_gemini_client",
        side_effect=RuntimeError("API key is not configured"),
    ):
        queries = await expand_search_queries("original question")

    assert queries == ["original question"]


@pytest.mark.asyncio
async def test_expand_search_queries_handles_empty_model_response():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text="")
    )

    with patch("app.services.llm.get_gemini_client", return_value=client):
        queries = await expand_search_queries("original question")

    assert queries == ["original question"]
