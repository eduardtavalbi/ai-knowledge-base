from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedDocumentFormatError(ValueError):
    pass


class InvalidDocumentFileError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSegment:
    text: str
    page_number: int | None = None
    section_title: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    segments: list[SourceSegment]


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    """Extract text and retain page/section metadata for later RAG citations."""
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentFormatError(extension)

    if extension in {".txt", ".md"}:
        try:
            raw_text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidDocumentFileError(
                "Text files must use UTF-8 encoding"
            ) from exc
        segments = _extract_text_segments(raw_text, markdown=extension == ".md")
        extracted_text = raw_text
    elif extension == ".pdf":
        segments = _extract_pdf_segments(content)
        extracted_text = "\n\n".join(segment.text for segment in segments)
    else:
        segments = _extract_docx_segments(content)
        extracted_text = "\n\n".join(segment.text for segment in segments)

    segments = [segment for segment in segments if segment.text.strip()]
    text = extracted_text
    if not text.strip():
        raise EmptyDocumentError("No readable text found in the uploaded file")

    return ExtractedDocument(text=text, segments=segments)


def extract_document_text(filename: str, content: bytes) -> str:
    """Backward-compatible text-only extraction helper."""
    return extract_document(filename, content).text


def _extract_text_segments(
    text: str,
    *,
    markdown: bool = False,
) -> list[SourceSegment]:
    segments: list[SourceSegment] = []
    current_section: str | None = None

    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if markdown:
            heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", block)
            if heading:
                current_section = heading.group(1).strip()
        segments.append(SourceSegment(text=block, section_title=current_section))

    return segments


def _extract_pdf_segments(content: bytes) -> list[SourceSegment]:
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise InvalidDocumentFileError(
                "Password-protected PDF files are not supported"
            )
        return [
            SourceSegment(text=page.extract_text() or "", page_number=page_number)
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    except InvalidDocumentFileError:
        raise
    except Exception as exc:
        raise InvalidDocumentFileError("Could not read the PDF file") from exc


def _extract_docx_segments(content: bytes) -> list[SourceSegment]:
    try:
        document = DocxDocument(BytesIO(content))
        segments: list[SourceSegment] = []
        current_section: str | None = None

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                style_name = block.style.name if block.style is not None else ""
                if style_name.startswith("Heading"):
                    current_section = text
                segments.append(
                    SourceSegment(text=text, section_title=current_section)
                )
            elif isinstance(block, Table):
                for row in block.rows:
                    text = " | ".join(
                        cell.text.strip() for cell in row.cells
                    ).strip()
                    if text:
                        segments.append(
                            SourceSegment(
                                text=text,
                                section_title=current_section,
                            )
                        )
        return segments
    except Exception as exc:
        # Treat parser errors from malformed DOCX packages as client input errors.
        raise InvalidDocumentFileError("Could not read the DOCX file") from exc
