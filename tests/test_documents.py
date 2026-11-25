from io import BytesIO

import pytest
from fastapi import Response, UploadFile
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.models.document_chunk import DocumentChunk
from conftest import TestingSessionLocal
from app.api.documents import upload_document

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
async def test_upload_rejects_missing_filename_with_clear_error():
    upload = UploadFile(filename=None, file=BytesIO(b"Document content"))

    with pytest.raises(Exception) as error:
        await upload_document(
            response=Response(),
            file=upload,
            db=None,
        )

    from fastapi import HTTPException

    assert isinstance(error.value, HTTPException)
    assert error.value.status_code == 400
    assert error.value.detail == "Filename is required"


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
        "detail": "Only .txt, .md, .pdf and .docx files are supported"
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

@pytest.mark.asyncio
async def test_upload_same_content_returns_existing_document(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        first = await client.post(
            "/documents/upload",
            files={"file": ("first.txt", b"Identical document content", "text/plain")},
        )
        second = await client.post(
            "/documents/upload",
            files={"file": ("renamed.md", b"Identical document content", "text/markdown")},
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["title"] == "first.txt"

    documents = await client.get("/documents/")
    assert len(documents.json()) == 1


@pytest.mark.asyncio
async def test_create_same_content_returns_existing_document(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        first = await client.post(
            "/documents/",
            json={"title": "Original", "content": "Same body"},
        )
        second = await client.post(
            "/documents/",
            json={"title": "Different title", "content": "Same body"},
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    documents = await client.get("/documents/")
    assert len(documents.json()) == 1


@pytest.mark.asyncio
async def test_update_rejects_content_used_by_another_document(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        first = await client.post(
            "/documents/",
            json={"title": "First", "content": "First body"},
        )
        second = await client.post(
            "/documents/",
            json={"title": "Second", "content": "Second body"},
        )

        response = await client.put(
            f"/documents/{second.json()['id']}",
            json={"title": "Second", "content": "First body"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Another document already has identical content"
    )

    unchanged = await client.get(f"/documents/{second.json()['id']}")
    assert unchanged.json()["content"] == "Second body"


@pytest.mark.asyncio
async def test_updated_content_fingerprint_is_used_for_deduplication(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.api.documents.save_document_chunks", new_callable=AsyncMock),
    ):
        created = await client.post(
            "/documents/",
            json={"title": "Before", "content": "Before update"},
        )
        document_id = created.json()["id"]

        updated = await client.put(
            f"/documents/{document_id}",
            json={"title": "After", "content": "After update"},
        )
        duplicate = await client.post(
            "/documents/",
            json={"title": "Duplicate", "content": "After update"},
        )

    assert updated.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == document_id



@pytest.mark.asyncio
async def test_upload_docx_extracts_paragraphs_and_tables(client):
    from io import BytesIO
    from docx import Document as WordDocument

    word_document = WordDocument()
    word_document.add_heading("Employee handbook", level=1)
    word_document.add_paragraph("Vacation policy: 20 days per year.")
    table = word_document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Region"
    table.rows[0].cells[1].text = "Allowance"
    buffer = BytesIO()
    word_document.save(buffer)

    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "handbook.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    extracted = response.json()["content"]
    assert "Employee handbook" in extracted
    assert "Vacation policy: 20 days per year." in extracted
    assert "Region | Allowance" in extracted


def _build_text_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"\nendstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)


@pytest.mark.asyncio
async def test_upload_pdf_extracts_text(client):
    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "policy.pdf",
                _build_text_pdf("Vacation policy: 20 days per year."),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert "Vacation policy: 20 days per year." in response.json()["content"]


@pytest.mark.asyncio
async def test_upload_pdf_without_extractable_text_is_rejected(client):
    from io import BytesIO
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)

    response = await client.post(
        "/documents/upload",
        files={"file": ("blank.pdf", buffer.getvalue(), "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "No readable text found in the uploaded file"
    )


@pytest.mark.asyncio
async def test_upload_invalid_docx_is_rejected(client):
    response = await client.post(
        "/documents/upload",
        files={
            "file": (
                "broken.docx",
                b"this is not a Word document",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Could not read the DOCX file"


@pytest.mark.asyncio
async def test_upload_invalid_pdf_is_rejected(client):
    response = await client.post(
        "/documents/upload",
        files={
            "file": ("broken.pdf", b"not a PDF", "application/pdf"),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Could not read the PDF file"


@pytest.mark.asyncio
async def test_update_replaces_old_chunks_and_clears_source_metadata(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.services.chunk_storage.generate_embedding", return_value=[0.0] * 384),
    ):
        uploaded = await client.post(
            "/documents/upload",
            files={
                "file": (
                    "policy.md",
                    b"# Old section\n\nOld searchable policy content.",
                    "text/markdown",
                )
            },
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        async with TestingSessionLocal() as db:
            before = (await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )).scalars().all()
            assert before
            assert any(chunk.source_section == "Old section" for chunk in before)

        updated = await client.put(
            f"/documents/{document_id}",
            json={
                "title": "Updated policy",
                "content": "Completely new plain text content.",
            },
        )

    assert updated.status_code == 200
    async with TestingSessionLocal() as db:
        after = (await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )).scalars().all()

    assert after
    assert all(chunk.source_page is None for chunk in after)
    assert all(chunk.source_section is None for chunk in after)
    assert all("Old searchable policy content" not in chunk.content for chunk in after)
    assert any("Completely new plain text content" in chunk.content for chunk in after)


@pytest.mark.asyncio
async def test_delete_document_also_deletes_its_chunks(client):
    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch("app.services.chunk_storage.generate_embedding", return_value=[0.0] * 384),
    ):
        created = await client.post(
            "/documents/",
            json={
                "title": "Document with chunks",
                "content": "Content that must disappear with its document.",
            },
        )
        assert created.status_code == 201
        document_id = created.json()["id"]

        async with TestingSessionLocal() as db:
            before = (await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )).scalars().all()
            assert before

        deleted = await client.delete(f"/documents/{document_id}")

    assert deleted.status_code == 200
    async with TestingSessionLocal() as db:
        remaining = (await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )).scalars().all()

    assert remaining == []
