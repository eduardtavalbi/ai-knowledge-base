from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.embeddings import generate_embedding


async def search_documents(
    query: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[dict]:
    query_embedding = generate_embedding(query)

    distance = Document.embedding.cosine_distance(query_embedding).label("distance")

    statement = (
        select(Document, distance)
        .where(Document.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )

    result = await db.execute(statement)

    documents = []

    for document, cosine_distance in result.all():
        documents.append({
            "id": document.id,
            "title": document.title,
            "content": document.content,
            "score": round(1 - cosine_distance, 4),
        })

    documents = [
        document
        for document in documents
        if document["score"] >= 0.45
    ]
    return documents