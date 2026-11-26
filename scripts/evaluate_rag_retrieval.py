"""Opt-in retrieval benchmark using the production multilingual embedding model.

Run only against a disposable PostgreSQL database:
    PG_TEST_DATABASE_URL=postgresql+asyncpg://... python -m scripts.evaluate_rag_retrieval
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document
from app.models.user import User
from app.models.user_session import SessionRefreshToken, UserSession
from app.services.chunk_storage import save_document_chunks
from app.services.search import search_document_chunks


DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "rag_retrieval_eval.json"
)
TOP_K = 5


def calculate_ranking_metrics(ranks: list[int | None], *, k: int = TOP_K) -> dict:
    """Calculate Recall@K and MRR@K from 1-based relevant-result ranks."""
    if not ranks:
        raise ValueError("At least one evaluated query is required")
    if k <= 0:
        raise ValueError("k must be positive")

    hits = [rank for rank in ranks if rank is not None and 1 <= rank <= k]
    reciprocal_ranks = [
        1.0 / rank if rank is not None and 1 <= rank <= k else 0.0
        for rank in ranks
    ]
    return {
        "queries": len(ranks),
        f"recall_at_{k}": round(len(hits) / len(ranks), 4),
        f"mrr_at_{k}": round(sum(reciprocal_ranks) / len(ranks), 4),
        "misses": len(ranks) - len(hits),
    }


def calculate_no_answer_metrics(retrieved_context: list[bool]) -> dict:
    """Report how often unanswerable queries still retrieve context."""
    if not retrieved_context:
        return {
            "no_answer_queries": 0,
            "no_answer_retrievals": 0,
            "no_answer_retrieval_rate_at_5": None,
        }
    retrievals = sum(retrieved_context)
    return {
        "no_answer_queries": len(retrieved_context),
        "no_answer_retrievals": retrievals,
        "no_answer_retrieval_rate_at_5": round(
            retrievals / len(retrieved_context), 4
        ),
    }


def load_dataset() -> dict:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    documents = dataset["documents"]
    queries = dataset["queries"]
    titles = {document["title"] for document in documents}

    if len(titles) != len(documents):
        raise ValueError("Evaluation document titles must be unique")
    if not queries:
        raise ValueError("Evaluation dataset must contain queries")

    query_ids = [query["id"] for query in queries]
    if len(query_ids) != len(set(query_ids)):
        raise ValueError("Evaluation query IDs must be unique")

    for query in queries:
        if query["language"] not in {"ru", "en"} or not query["query"].strip():
            raise ValueError(f"Query {query['id']} has invalid language or empty text")
        answerable = query.get("answerable", True)
        expected_titles = query.get("expected_titles", [])
        if answerable and (
            not expected_titles or not set(expected_titles) <= titles
        ):
            raise ValueError(
                f"Answerable query {query['id']} has invalid expected documents"
            )
        if not answerable and expected_titles:
            raise ValueError(
                f"Unanswerable query {query['id']} must not have expected documents"
            )
    return dataset


async def run_benchmark() -> dict:
    database_url = os.getenv("PG_TEST_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Set PG_TEST_DATABASE_URL to a disposable PostgreSQL database; "
            "the benchmark creates and drops a temporary schema."
        )

    dataset = load_dataset()
    schema = f"rag_eval_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = None

    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        engine = create_async_engine(
            database_url,
            connect_args={
                "server_settings": {
                    "search_path": f"{schema},public",
                }
            },
        )
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    checkfirst=False,
                )
            )

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        ranks: list[int | None] = []
        no_answer_retrievals: list[bool] = []
        query_results = []

        async with session_factory() as session:
            user = User(
                email=f"{schema}@example.test",
                hashed_password="evaluation-only-not-a-login",
            )
            session.add(user)
            await session.flush()

            for item in dataset["documents"]:
                document = Document(
                    user_id=user.id,
                    title=item["title"],
                    content=item["content"],
                    content_sha256=hashlib.sha256(
                        item["content"].encode("utf-8")
                    ).hexdigest(),
                )
                session.add(document)
                await session.flush()
                await save_document_chunks(document, session)

            await session.commit()

            for case in dataset["queries"]:
                # Isolate retrieval from Gemini query-rewrite variability. The
                # production embedding model and PostgreSQL retrievers remain real.
                with patch(
                    "app.services.llm.expand_search_queries",
                    new_callable=AsyncMock,
                    return_value=[case["query"]],
                ):
                    results = await search_document_chunks(
                        case["query"],
                        session,
                        user_id=user.id,
                        limit=TOP_K,
                    )

                answerable = case.get("answerable", True)
                expected = set(case.get("expected_titles", []))
                rank = next(
                    (
                        index
                        for index, result in enumerate(results, start=1)
                        if result["title"] in expected
                    ),
                    None,
                )
                if answerable:
                    ranks.append(rank)
                else:
                    no_answer_retrievals.append(bool(results))
                query_results.append({
                    "id": case["id"],
                    "language": case["language"],
                    "answerable": answerable,
                    "relevant_rank": rank,
                    "retrieved_any_context": bool(results),
                    "retrieved_titles": [item["title"] for item in results],
                })

        metrics = calculate_ranking_metrics(ranks)
        metrics.update(calculate_no_answer_metrics(no_answer_retrievals))
        return {
            "dataset_version": dataset["version"],
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "retrieval": "PostgreSQL hybrid vector + Russian/English full-text with RRF",
            "query_expansion": "disabled for this benchmark to isolate retrieval",
            "metrics": metrics,
            "results": query_results,
        }
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            )
        await admin_engine.dispose()


def main() -> None:
    result = asyncio.run(run_benchmark())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
