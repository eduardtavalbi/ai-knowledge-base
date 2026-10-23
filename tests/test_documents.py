import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_document(client):
    response = await client.post(
        "/documents/",
        json={
            "title": "Тестовый документ",
            "content": "Содержимое для автоматического теста.",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["title"] == "Тестовый документ"
    assert data["content"] == "Содержимое для автоматического теста."



@pytest.mark.asyncio
async def test_get_documents(client):
    await client.post(
        "/documents/",
        json={
            "title": "Первый документ",
            "content": "Первое содержимое.",
        },
    )

    response = await client.get("/documents/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Первый документ"
    assert data[0]["content"] == "Первое содержимое."


@pytest.mark.asyncio
async def test_get_document_by_id(client):
    create_response = await client.post(
        "/documents/",
        json={
            "title": "Документ по ID",
            "content": "Проверяем получение одной записи.",
        },
    )

    document_id = create_response.json()["id"]

    response = await client.get(f"/documents/{document_id}")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == document_id
    assert data["title"] == "Документ по ID"
    assert data["content"] == "Проверяем получение одной записи."


@pytest.mark.asyncio
async def test_get_nonexistent_document(client):
    response = await client.get("/documents/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


@pytest.mark.asyncio
async def test_update_document(client):
    create_response = await client.post(
        "/documents/",
        json={
            "title": "Старое название",
            "content": "Старое содержимое.",
        },
    )

    document_id = create_response.json()["id"]

    response = await client.put(
        f"/documents/{document_id}",
        json={
            "title": "Новое название",
            "content": "Новое содержимое.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == document_id
    assert data["title"] == "Новое название"
    assert data["content"] == "Новое содержимое."


@pytest.mark.asyncio
async def test_delete_document(client):
    create_response = await client.post(
        "/documents/",
        json={
            "title": "Документ для удаления",
            "content": "Этот документ будет удалён тестом.",
        },
    )

    document_id = create_response.json()["id"]

    response = await client.delete(f"/documents/{document_id}")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Document deleted successfully"
    }

    get_response = await client.get(f"/documents/{document_id}")

    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_upload_text_file(client):
    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "test_document.txt",
                "Содержимое тестового файла.".encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["title"] == "test_document.txt"
    assert data["content"] == "Содержимое тестового файла."



@pytest.mark.asyncio
async def test_upload_unsupported_file(client):
    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "malware.exe",
                b"test content",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Only .txt and .md files are supported"
    }


@pytest.mark.asyncio
async def test_upload_file_too_large(client):
    large_content = b"a" * (2 * 1024 * 1024 + 1)

    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "large.txt",
                large_content,
                "text/plain",
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "File is too large. Maximum size is 2 MB"
    }



@pytest.mark.asyncio
async def test_upload_markdown_file(client):
    markdown_content = (
        "# Моя база знаний\n\n"
        "## Python\n"
        "- FastAPI\n"
        "- PostgreSQL\n"
    )

    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "knowledge.md",
                markdown_content.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "knowledge.md"
    assert data["content"] == markdown_content


@pytest.mark.asyncio
async def test_search_documents(client):
    with patch(
        "app.api.documents.search_documents",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []

        response = await client.get(
            "/documents/search",
            params={"q": "Как сократить расходы", "limit": 5},
        )

    assert response.status_code == 200
    assert response.json() == []
    mock_search.assert_awaited_once()
    assert mock_search.await_args.kwargs["query"] == "Как сократить расходы"
    assert mock_search.await_args.kwargs["limit"] == 5

@pytest.mark.asyncio
async def test_search_documents_empty_query(client):
    response = await client.get(
        "/documents/search",
        params={"q": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Search query cannot be empty"

@pytest.mark.asyncio
async def test_search_documents_invalid_limit(client):
    response = await client.get(
        "/documents/search",
        params={"q": "Python", "limit": 21},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Limit must be between 1 and 20"

@pytest.mark.asyncio
async def test_search_documents_zero_limit(client):
    response = await client.get(
        "/documents/search",
        params={"q": "Python", "limit": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Limit must be between 1 and 20"

@pytest.mark.asyncio
async def test_search_documents_max_limit(client):
    with patch(
        "app.api.documents.search_documents",
        new_callable=AsyncMock,
    ) as mock_search:
        mock_search.return_value = []

        response = await client.get(
            "/documents/search",
            params={"q": "Python", "limit": 20},
        )

    assert response.status_code == 200
    assert response.json() == []
    assert mock_search.await_args.kwargs["limit"] == 20