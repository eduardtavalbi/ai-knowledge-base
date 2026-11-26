import asyncio
from difflib import SequenceMatcher
import re
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import generate_embedding, generate_embeddings


_NEGATION_PATTERN = re.compile(
    r"\b(?:not|no|never|without|cannot|can't|не|нет|ни|никогда|без)\b",
    re.IGNORECASE,
)
_CURRENT_VERSION_PATTERN = re.compile(
    r"\b(?:current|latest|newest|active|in force|currently|now|"
    r"текущ\w*|актуальн\w*|действующ\w*|последн\w*|сейчас)\b",
    re.IGNORECASE,
)
_SUPERSEDED_PATTERN = re.compile(
    r"\b(?:superseded|outdated|obsolete|deprecated|replaced by|"
    r"no longer in effect|устаревш\w*|замен[её]н\w*|"
    r"не действует|утратил[ао]?\s+силу)\b",
    re.IGNORECASE,
)
_SUPERSEDED_RANK_WEIGHT = 0.1


def _prefers_current_version(query: str) -> bool:
    return bool(_CURRENT_VERSION_PATTERN.search(query))


def _is_superseded_document(document: Document) -> bool:
    # Inspect both title and full text once per document. Keep historical
    # documents searchable; only down-rank explicitly superseded ones when
    # the user's query asks for the current/latest policy.
    return bool(
        _SUPERSEDED_PATTERN.search(
            f"{document.title}\n{document.content}"
        )
    )


def _negation_signature(text: str) -> frozenset[str]:
    """Return explicit negation markers so contradictory text is not deduplicated."""
    return frozenset(
        match.group(0).lower()
        for match in _NEGATION_PATTERN.finditer(text)
    )


def _multilingual_fts_expressions(text_expression, query: str):
    """Build Russian + English PostgreSQL FTS expressions for mixed-language data."""
    russian_vector = func.to_tsvector("russian", text_expression)
    english_vector = func.to_tsvector("english", text_expression)
    search_vector = russian_vector.op("||")(english_vector)

    russian_query = func.plainto_tsquery("russian", query)
    english_query = func.plainto_tsquery("english", query)
    search_query = russian_query.op("||")(english_query)
    return search_vector, search_query





async def search_documents(
    query: str,
    db: AsyncSession,
    user_id: int,
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
            Document.user_id == user_id,
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
    search_text = func.concat_ws(
        " ",
        Document.title,
        Document.content,
    )
    search_vector, search_query = _multilingual_fts_expressions(
        search_text,
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
        .where(Document.user_id == user_id, search_vector.op("@@")(search_query))
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
    # SentenceTransformer inference is synchronous; keep it off the event loop.
    query_embedding = await asyncio.to_thread(generate_embedding, query)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    semantic_statement = (
        select(Document, distance)
        .join(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        )
        .where(Document.user_id == user_id, DocumentChunk.embedding.is_not(None))
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


def _prepare_search_queries(
    original_query: str,
    expanded_queries: list[str],
    max_queries: int = 3,
) -> list[str]:
    """Keep the user's exact query and add only distinct, bounded alternatives."""
    original = original_query.strip()
    if not original:
        return []

    queries = [original]
    for candidate in expanded_queries:
        if not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        if not candidate or len(candidate) > 200:
            continue

        normalized = candidate.casefold()
        is_duplicate = any(
            normalized == existing.casefold()
            or SequenceMatcher(
                None, normalized, existing.casefold()
            ).ratio() >= 0.85
            for existing in queries
        )
        if not is_duplicate:
            queries.append(candidate)
        if len(queries) >= max(1, max_queries):
            break

    return queries[:max(1, max_queries)]


async def search_document_chunks(
    query: str,
    db: AsyncSession,
    user_id: int,
    limit: int = 5,
) -> list[dict]:
    if not query.strip() or limit <= 0:
        return []

    from app.services.llm import expand_search_queries

    expanded_queries = await expand_search_queries(query, max_queries=3)
    queries = _prepare_search_queries(query, expanded_queries, max_queries=3)
    reciprocal_rank_constant = 60
    candidate_limit = limit * 10
    scores: dict[int, float] = {}
    chunks_by_id: dict[int, dict] = {}
    prefer_current_version = _prefers_current_version(query)
    superseded_by_document: dict[int, bool] = {}

    def add_ranked_results(rows, *, semantic: bool = False) -> None:
        for rank, (document, chunk, raw_score, *_) in enumerate(rows, start=1):
            if semantic:
                # Preserve the established minimum cosine-similarity threshold.
                # pgvector returns cosine distance, so similarity = 1 - distance.
                if raw_score is None or (1.0 - float(raw_score)) < 0.45:
                    continue

            chunks_by_id[chunk.id] = {
                "document_id": document.id,
                "title": document.title,
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "source_page": chunk.source_page,
                "source_section": chunk.source_section,
            }
            contribution = 1.0 / (reciprocal_rank_constant + rank)
            if prefer_current_version:
                if document.id not in superseded_by_document:
                    superseded_by_document[document.id] = (
                        _is_superseded_document(document)
                    )
                if superseded_by_document[document.id]:
                    contribution *= _SUPERSEDED_RANK_WEIGHT

            scores[chunk.id] = scores.get(chunk.id, 0.0) + contribution

    # Encode all query variants in one worker-thread call. SentenceTransformer
    # inference is synchronous/CPU-bound; batching avoids repeated model setup
    # and keeps the async event loop responsive.
    query_embeddings = await asyncio.to_thread(generate_embeddings, queries)
    if len(query_embeddings) != len(queries):
        raise RuntimeError("Embedding count does not match search query count")

    for search_query, query_embedding in zip(queries, query_embeddings, strict=True):
        distance = DocumentChunk.embedding.cosine_distance(
            query_embedding
        ).label("raw_score")

        # Keep each retriever's ORDER BY + LIMIT inside its own subquery.
        # PostgreSQL can therefore use the cosine HNSW index for the semantic
        # candidate scan before the two candidate sets are combined.
        semantic_candidates = (
            select(
                DocumentChunk.id.label("chunk_id"),
                distance.label("raw_score"),
                literal("semantic").label("retriever"),
                distance.label("sort_score"),
            )
            .where(
                DocumentChunk.embedding.is_not(None),
                select(Document.id)
                .where(
                    Document.id == DocumentChunk.document_id,
                    Document.user_id == user_id,
                )
                .exists(),
            )
            .order_by(distance)
            .limit(candidate_limit)
            .subquery()
        )

        search_text = func.concat_ws(
            " ",
            Document.title,
            DocumentChunk.content,
        )
        search_vector, search_tsquery = _multilingual_fts_expressions(
            search_text,
            search_query,
        )
        text_rank = func.ts_rank(search_vector, search_tsquery)
        text_candidates = (
            select(
                DocumentChunk.id.label("chunk_id"),
                text_rank.label("raw_score"),
                literal("text").label("retriever"),
                (-text_rank).label("sort_score"),
            )
            .join(
                Document,
                DocumentChunk.document_id == Document.id,
            )
            .where(
                Document.user_id == user_id,
                search_vector.op("@@")(search_tsquery),
            )
            .order_by(text_rank.desc())
            .limit(candidate_limit)
            .subquery()
        )

        candidates = union_all(
            select(
                semantic_candidates.c.chunk_id,
                semantic_candidates.c.raw_score,
                semantic_candidates.c.retriever,
                semantic_candidates.c.sort_score,
            ),
            select(
                text_candidates.c.chunk_id,
                text_candidates.c.raw_score,
                text_candidates.c.retriever,
                text_candidates.c.sort_score,
            ),
        ).subquery()

        statement = (
            select(
                Document,
                DocumentChunk,
                candidates.c.raw_score,
                candidates.c.retriever,
            )
            .join(
                DocumentChunk,
                DocumentChunk.id == candidates.c.chunk_id,
            )
            .join(
                Document,
                Document.id == DocumentChunk.document_id,
            )
            # Repeat tenant filtering outside the candidate subqueries as a
            # defense-in-depth invariant; both retrievers also filter inside.
            .where(Document.user_id == user_id)
            .order_by(candidates.c.retriever, candidates.c.sort_score)
        )
        result_rows = (await db.execute(statement)).all()
        semantic_rows = [
            (document, chunk, raw_score)
            for document, chunk, raw_score, retriever in result_rows
            if retriever == "semantic"
        ]
        text_rows = [
            (document, chunk, raw_score)
            for document, chunk, raw_score, retriever in result_rows
            if retriever == "text"
        ]
        add_ranked_results(semantic_rows, semantic=True)
        add_ranked_results(text_rows)

    if not scores:
        return []

    max_score = max(scores.values())
    ranked_chunks = sorted(
        scores,
        key=lambda chunk_id: scores[chunk_id],
        reverse=True,
    )

    chunks: list[dict] = []
    chunks_by_document: dict[int, list[str]] = {}
    max_chunks_per_document = 2
    duplicate_threshold = 0.90

    for chunk_id in ranked_chunks:
        item = chunks_by_id[chunk_id]
        normalized_content = re.sub(
            r"\s+",
            " ",
            item["content"],
        ).strip().lower()

        existing_chunks = chunks_by_document.get(item["document_id"], [])
        if len(existing_chunks) >= max_chunks_per_document:
            continue

        current_negation = _negation_signature(normalized_content)
        is_duplicate = any(
            current_negation == _negation_signature(existing_content)
            and SequenceMatcher(
                None,
                normalized_content,
                existing_content,
            ).ratio() >= duplicate_threshold
            for existing_content in existing_chunks
        )
        if is_duplicate:
            continue

        chunks_by_document.setdefault(item["document_id"], []).append(
            normalized_content
        )
        chunks.append({
            **item,
            # Relative fused score (0..1), not a cosine similarity.
            "score": round(scores[chunk_id] / max_score, 4),
        })

        if len(chunks) >= limit:
            break

    return chunks
