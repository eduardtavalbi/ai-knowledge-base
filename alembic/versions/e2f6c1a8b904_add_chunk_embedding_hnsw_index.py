"""add approximate nearest-neighbor index for chunk embeddings

Revision ID: e2f6c1a8b904
Revises: 4f8b2a1c9d30
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2f6c1a8b904"
down_revision: Union[str, Sequence[str], None] = "4f8b2a1c9d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Match the cosine-distance operator used by semantic retrieval.
    # A partial index keeps NULL embeddings out of the ANN structure.
    op.execute(
        """
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
