from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunking import split_text
from app.services.document_extraction import SourceSegment
from app.services.embeddings import generate_embedding


def _group_source_segments(
    segments: Sequence[SourceSegment],
) -> list[SourceSegment]:
    """Combine adjacent blocks with identical provenance before chunking."""
    grouped: list[SourceSegment] = []
    for segment in segments:
        if not segment.text.strip():
            continue
        if (
            grouped
            and grouped[-1].page_number == segment.page_number
            and grouped[-1].section_title == segment.section_title
        ):
            previous = grouped[-1]
            grouped[-1] = SourceSegment(
                text=f"{previous.text}\n\n{segment.text}",
                page_number=previous.page_number,
                section_title=previous.section_title,
            )
        else:
            grouped.append(segment)
    return grouped


async def save_document_chunks(
    document: Document,
    db: AsyncSession,
    source_segments: Sequence[SourceSegment] | None = None,
) -> None:
    segments = source_segments or [SourceSegment(text=document.content)]
    chunk_index = 0

    for segment in _group_source_segments(segments):
        for chunk_content in split_text(segment.text):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_content,
                source_page=segment.page_number,
                source_section=segment.section_title,
                embedding=generate_embedding(chunk_content),
            )
            db.add(chunk)
            chunk_index += 1

    await db.flush()
