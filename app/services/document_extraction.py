from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile

from docx import Document as DocxDocument
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class UnsupportedDocumentFormatError(ValueError):
    pass


class InvalidDocumentFileError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def extract_document_text(filename: str, content: bytes) -> str:
    """Extract UTF-8 text from supported knowledge-base upload formats."""
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentFormatError(extension)

    if extension in {".txt", ".md"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidDocumentFileError(
                "Text files must use UTF-8 encoding"
            ) from exc
    elif extension == ".pdf":
        text = _extract_pdf_text(content)
    else:
        text = _extract_docx_text(content)

    if not text.strip():
        raise EmptyDocumentError("No readable text found in the uploaded file")

    return text


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise InvalidDocumentFileError(
                    "Password-protected PDF files are not supported"
                )
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except InvalidDocumentFileError:
        raise
    except (PdfReadError, EOFError, ValueError, OSError) as exc:
        raise InvalidDocumentFileError("Could not read the PDF file") from exc


def _extract_docx_text(content: bytes) -> str:
    try:
        document = DocxDocument(BytesIO(content))
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise InvalidDocumentFileError("Could not read the DOCX file") from exc

    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))

    return "\n".join(part for part in parts if part.strip())
