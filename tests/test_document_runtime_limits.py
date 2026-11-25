import threading
from unittest.mock import AsyncMock, patch

import pytest

from app.services.document_extraction import ExtractedDocument, SourceSegment


@pytest.mark.asyncio
async def test_upload_document_extraction_runs_off_event_loop_thread(client):
    event_loop_thread = threading.get_ident()
    extraction_thread = None

    def extract_in_worker_thread(*, filename, content):
        nonlocal extraction_thread
        extraction_thread = threading.get_ident()
        return ExtractedDocument(
            text="Extracted document content",
            segments=[SourceSegment(text="Extracted document content")],
        )

    with (
        patch(
            "app.api.documents.extract_document",
            side_effect=extract_in_worker_thread,
        ),
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch(
            "app.api.documents.save_document_chunks",
            new_callable=AsyncMock,
        ),
    ):
        response = await client.post(
            "/documents/upload",
            files={"file": ("document.txt", b"Document content", "text/plain")},
        )

    assert response.status_code == 201
    assert extraction_thread is not None
    assert extraction_thread != event_loop_thread


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/documents/search", "/documents/search/chunks"],
)
async def test_search_endpoints_reject_queries_over_2000_characters(client, path):
    response = await client.get(path, params={"q": "x" * 2001})

    assert response.status_code == 422
