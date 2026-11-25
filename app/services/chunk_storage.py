import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunking import split_text
from app.services.document_extraction import SourceSegment
from app.services.embeddings import generate_embeddings


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
                text=f"{previous.text}\\n\\n{segment.text}",
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
    chunk_data: list[tuple[str, int | None, str | None]] = []

    for segment in _group_source_segments(segments):
        for chunk_content in split_text(segment.text):
            chunk_data.append((
                chunk_content,
                segment.page_number,
                segment.section_title,
            ))

    if not chunk_data:
        return

    # SentenceTransformer inference is CPU-bound and synchronous. Run one
    # batched inference call in a worker thread so uploads do not block the
    # async API event loop while embeddings are being generated.
    embeddings = await asyncio.to_thread(
        generate_embeddings,
        [content for content, _, _ in chunk_data],
    )

    if len(embeddings) != len(chunk_data):
        raise RuntimeError("Embedding count does not match document chunk count")

    for chunk_index, ((chunk_content, source_page, source_section), embedding) in enumerate(
        zip(chunk_data, embeddings, strict=True)
    ):
        db.add(DocumentChunk(
            document_id=document.id,
            chunk_index=chunk_index,
            content=chunk_content,
            source_page=source_page,
            source_section=source_section,
            embedding=embedding,
        ))

    await db.flush()
