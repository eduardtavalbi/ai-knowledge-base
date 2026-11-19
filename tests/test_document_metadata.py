from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docx import Document as WordDocument

from app.models.document import Document
from app.services.chunk_storage import save_document_chunks
from app.services.document_extraction import SourceSegment, extract_document


def test_markdown_extraction_tracks_heading_and_preserves_source_text():
    source = "# HR policies\n\nVacation allowance is 20 days.\n\n## Sick leave\n\nPaid sick leave is available."

    extracted = extract_document("policies.md", source.encode("utf-8"))

    assert extracted.text == source
    assert extracted.segments[0].section_title == "HR policies"
    assert extracted.segments[1].section_title == "HR policies"
    assert extracted.segments[2].section_title == "Sick leave"
    assert extracted.segments[3].section_title == "Sick leave"


def test_docx_extraction_tracks_heading_for_paragraphs_and_tables():
    word = WordDocument()
    word.add_heading("Vacation policy", level=1)
    word.add_paragraph("Employees receive 20 days.")
    table = word.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Country"
    table.rows[0].cells[1].text = "Allowance"
    word.add_heading("Sick leave", level=1)
    word.add_paragraph("Employees can take paid sick leave.")
    buffer = BytesIO()
    word.save(buffer)

    extracted = extract_document("handbook.docx", buffer.getvalue())

    assert extracted.segments[0].section_title == "Vacation policy"
    assert extracted.segments[1].section_title == "Vacation policy"
    assert extracted.segments[2].text == "Country | Allowance"
    assert extracted.segments[2].section_title == "Vacation policy"
    assert extracted.segments[-1].section_title == "Sick leave"


def test_pdf_extraction_tracks_one_based_page_numbers(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        def __init__(self, *_args, **_kwargs):
            self.is_encrypted = False
            self.pages = [FakePage("Page one text"), FakePage("Page two text")]

    monkeypatch.setattr("app.services.document_extraction.PdfReader", FakeReader)

    extracted = extract_document("manual.pdf", b"fake pdf bytes")

    assert [segment.page_number for segment in extracted.segments] == [1, 2]
    assert extracted.segments[0].text == "Page one text"
    assert extracted.segments[1].text == "Page two text"


@pytest.mark.asyncio
async def test_chunk_storage_persists_source_page_and_section():
    document = Document(id=42, title="Policy", content="Vacation policy details.")
    db = MagicMock()
    db.flush = AsyncMock()
    source_segments = [
        SourceSegment(
            text="Vacation policy details.",
            page_number=3,
            section_title="Annual leave",
        )
    ]

    with patch(
        "app.services.chunk_storage.generate_embedding",
        return_value=[0.0] * 384,
    ):
        await save_document_chunks(document, db, source_segments=source_segments)

    stored_chunk = db.add.call_args.args[0]
    assert stored_chunk.document_id == 42
    assert stored_chunk.source_page == 3
    assert stored_chunk.source_section == "Annual leave"
    assert stored_chunk.content == "Vacation policy details."
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_chunk_storage_keeps_metadata_when_combining_paragraphs():
    document = Document(id=7, title="Policy", content="First paragraph. Second paragraph.")
    db = MagicMock()
    db.flush = AsyncMock()
    source_segments = [
        SourceSegment("First paragraph.", page_number=2, section_title="Benefits"),
        SourceSegment("Second paragraph.", page_number=2, section_title="Benefits"),
    ]

    with patch(
        "app.services.chunk_storage.generate_embedding",
        return_value=[0.0] * 384,
    ):
        await save_document_chunks(document, db, source_segments=source_segments)

    stored_chunk = db.add.call_args.args[0]
    assert stored_chunk.source_page == 2
    assert stored_chunk.source_section == "Benefits"
    assert "First paragraph." in stored_chunk.content
    assert "Second paragraph." in stored_chunk.content



@pytest.mark.asyncio
async def test_docx_upload_passes_section_metadata_to_chunk_storage(client):
    word = WordDocument()
    word.add_heading("Remote work policy", level=1)
    word.add_paragraph("Employees may work remotely.")
    buffer = BytesIO()
    word.save(buffer)

    with (
        patch("app.api.documents.generate_embedding", return_value=[0.0] * 384),
        patch(
            "app.api.documents.save_document_chunks",
            new_callable=AsyncMock,
        ) as save_chunks,
    ):
        response = await client.post(
            "/documents/upload",
            files={
                "file": (
                    "remote-policy.docx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert response.status_code == 201
    save_chunks.assert_awaited_once()
    segments = save_chunks.await_args.kwargs["source_segments"]
    assert any(
        segment.section_title == "Remote work policy"
        and "Employees may work remotely." in segment.text
        for segment in segments
    )
