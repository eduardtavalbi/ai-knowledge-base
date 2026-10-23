from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.embeddings import generate_embedding

async def search_documents(
        query:str,
        db:AsyncSession,
        limit:int = 5
) -> list[Document]:
    query_embedding = generate_embedding(query)

    statement = (
        select(Document)
        .where(Document.embedding.is_not(None))
        .order_by(Document.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    result = await db.execute(statement)

    return list(result.scalars().all())
