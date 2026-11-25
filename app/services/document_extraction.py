from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


class UnsupportedDocumentFormatError(ValueError):
    pass


class InvalidDocumentFileError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


class DocumentTooLargeError(ValueError):
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
MAX_EXTRACTED_TEXT_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_DOCX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_DOCX_ARCHIVE_ENTRIES = 1000


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

    _validate_extracted_text_size(extracted_text)
    segments = [segment for segment in segments if segment.text.strip()]
    if not extracted_text.strip():
        raise EmptyDocumentError("No readable text found in the uploaded file")

    return ExtractedDocument(text=extracted_text, segments=segments)


def extract_document_text(filename: str, content: bytes) -> str:
    """Backward-compatible text-only extraction helper."""
    return extract_document(filename, content).text


def _validate_extracted_text_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_EXTRACTED_TEXT_BYTES:
        raise DocumentTooLargeError(
            "Extracted document text exceeds the 2 MB limit"
        )


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
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentTooLargeError(
                f"PDF files cannot contain more than {MAX_PDF_PAGES} pages"
            )

        segments: list[SourceSegment] = []
        extracted_bytes = 0
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            extracted_bytes += len(page_text.encode("utf-8"))
            if extracted_bytes > MAX_EXTRACTED_TEXT_BYTES:
                raise DocumentTooLargeError(
                    "Extracted document text exceeds the 2 MB limit"
                )
            segments.append(
                SourceSegment(text=page_text, page_number=page_number)
            )
        return segments
    except (InvalidDocumentFileError, DocumentTooLargeError):
        raise
    except Exception as exc:
        raise InvalidDocumentFileError("Could not read the PDF file") from exc


def _validate_docx_package(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ARCHIVE_ENTRIES:
                raise DocumentTooLargeError(
                    "DOCX package contains too many archive entries"
                )
            uncompressed_size = sum(entry.file_size for entry in entries)
            if uncompressed_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise DocumentTooLargeError(
                    "DOCX package expands beyond the 20 MB processing limit"
                )
            if content and uncompressed_size / len(content) > 200:
                raise DocumentTooLargeError(
                    "DOCX package compression ratio is too high"
                )
    except (DocumentTooLargeError, zipfile.BadZipFile):
        raise
    except Exception as exc:
        raise InvalidDocumentFileError("Could not read the DOCX file") from exc


def _extract_docx_segments(content: bytes) -> list[SourceSegment]:
    try:
        _validate_docx_package(content)
        document = DocxDocument(BytesIO(content))
        segments: list[SourceSegment] = []
        current_section: str | None = None
        extracted_bytes = 0

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue
                style_name = block.style.name if block.style is not None else ""
                if style_name.startswith("Heading"):
                    current_section = text
                segment = SourceSegment(text=text, section_title=current_section)
                extracted_bytes += len(text.encode("utf-8")) + 2
                if extracted_bytes > MAX_EXTRACTED_TEXT_BYTES:
                    raise DocumentTooLargeError(
                        "Extracted document text exceeds the 2 MB limit"
                    )
                segments.append(segment)
            elif isinstance(block, Table):
                for row in block.rows:
                    text = " | ".join(
                        cell.text.strip() for cell in row.cells
                    ).strip()
                    if text:
                        extracted_bytes += len(text.encode("utf-8")) + 2
                        if extracted_bytes > MAX_EXTRACTED_TEXT_BYTES:
                            raise DocumentTooLargeError(
                                "Extracted document text exceeds the 2 MB limit"
                            )
                        segments.append(
                            SourceSegment(
                                text=text,
                                section_title=current_section,
                            )
                        )
        return segments
    except (DocumentTooLargeError, InvalidDocumentFileError):
        raise
    except Exception as exc:
        # Treat parser errors from malformed DOCX packages as client input errors.
        raise InvalidDocumentFileError("Could not read the DOCX file") from exc
