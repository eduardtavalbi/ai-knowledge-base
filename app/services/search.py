from difflib import SequenceMatcher
import re
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import generate_embedding





async def search_documents(
    query: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[dict]:
    normalized_query = query.strip().lower()

    if not normalized_query or limit <= 0:
        return []

    documents: list[dict] = []
    seen_ids: set[int] = set()

    def add_document(
        document: Document,
        score: float,
    ) -> None:
        if document.id in seen_ids:
            return

        seen_ids.add(document.id)
        documents.append({
            "id": document.id,
            "title": document.title,
            "content": document.content,
            "score": score,
        })

    # 1. Точное совпадение по названию.
    title_statement = (
        select(Document)
        .where(
            func.lower(Document.title).contains(
                normalized_query,
                autoescape=True,
            )
        )
        .order_by(Document.id.desc())
        .limit(limit)
    )

    title_result = await db.execute(title_statement)

    for document in title_result.scalars().all():
        add_document(document, 1.0)

    if len(documents) >= limit:
        return documents

    # 2. Полнотекстовый поиск PostgreSQL с русской морфологией.
    search_vector = func.to_tsvector(
        "russian",
        func.concat_ws(
            " ",
            Document.title,
            Document.content,
        ),
    )
    search_query = func.plainto_tsquery(
        "russian",
        query,
    )

    text_statement = (
        select(
            Document,
            func.ts_rank(
                search_vector,
                search_query,
            ).label("rank"),
        )
        .where(search_vector.op("@@")(search_query))
        .order_by(
            func.ts_rank(
                search_vector,
                search_query,
            ).desc()
        )
        .limit(limit)
    )

    text_result = await db.execute(text_statement)

    for document, rank in text_result.all():
        add_document(document, float(rank))

    if documents:
        return documents[:limit]

    # 3. Семантический поиск дополняет результаты.
    query_embedding = generate_embedding(query)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    semantic_statement = (
        select(Document, distance)
        .join(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit * 10)
    )

    semantic_result = await db.execute(semantic_statement)

    for document, cosine_distance in semantic_result.all():
        score = round(1 - cosine_distance, 4)

        if score < 0.45:
            continue

        add_document(document, score)

        if len(documents) >= limit:
            break

    return documents


async def search_document_chunks(
    query: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[dict]:
    query_embedding = generate_embedding(query)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    statement = (
        select(Document, DocumentChunk, distance)
        .join(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit * 10)
    )

    result = await db.execute(statement)

    chunks = []
    chunks_by_document: dict[int, list[str]] = {}
    min_score = 0.45
    max_chunks_per_document = 2
    duplicate_threshold = 0.90

    for document, chunk, cosine_distance in result.all():
        score = round(1 - cosine_distance, 4)

        if score < min_score:
            continue

        normalized_content = re.sub(
            r"\s+",
            " ",
            chunk.content,
        ).strip().lower()

        existing_chunks = chunks_by_document.get(
            document.id,
            [],
        )

        if len(existing_chunks) >= max_chunks_per_document:
            continue

        is_duplicate = any(
            SequenceMatcher(
                None,
                normalized_content,
                existing_content,
            ).ratio() >= duplicate_threshold
            for existing_content in existing_chunks
        )

        if is_duplicate:
            continue

        chunks_by_document.setdefault(
            document.id,
            [],
        ).append(normalized_content)

        chunks.append({
            "document_id": document.id,
            "title": document.title,
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": score,
        })

        if len(chunks) >= limit:
            break

    return chunks
