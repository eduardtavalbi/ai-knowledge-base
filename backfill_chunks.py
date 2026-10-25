import asyncio

from sqlalchemy import select, func
from app.db.session import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunk_storage import save_document_chunks


async def main():
    generator = get_db()
    db = await generator.__anext__()

    try:
        result = await db.execute(
            select(Document).where(
                ~select(DocumentChunk.id)
                .where(DocumentChunk.document_id == Document.id)
                .exists()
            )
        )
        documents = result.scalars().all()

        print(f"Документов без чанков: {len(documents)}")

        if not documents:
            print("Все документы уже имеют чанки.")
            return

        for document in documents:
            await save_document_chunks(document, db)
            print(f"Обработан документ ID={document.id}: {document.title}")

        await db.commit()

        result = await db.execute(
            select(func.count()).select_from(DocumentChunk)
        )
        print(f"Всего чанков после обработки: {result.scalar()}")

    except Exception:
        await db.rollback()
        raise
    finally:
        await generator.aclose()


if __name__ == "__main__":
    asyncio.run(main())
