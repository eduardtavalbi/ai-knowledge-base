from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunking import split_text
from app.services.embeddings import generate_embedding


async def save_document_chunks(
    document: Document,
    db: AsyncSession,
) -> None:
    chunks = split_text(document.content)

    for index, chunk_content in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=chunk_content,
            embedding=generate_embedding(chunk_content),
        )
        db.add(chunk)

    await db.flush()
