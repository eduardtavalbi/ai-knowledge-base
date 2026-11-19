"""add SHA-256 content fingerprint to documents

Revision ID: d1a4c8e92f10
Revises: ca9b2ff54088
Create Date: 2026-11-19
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d1a4c8e92f10"
down_revision: Union[str, Sequence[str], None] = "ca9b2ff54088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )

    connection = op.get_bind()
    documents = sa.table(
        "documents",
        sa.column("id", sa.Integer()),
        sa.column("content", sa.Text()),
        sa.column("content_sha256", sa.String(length=64)),
    )

    # Preserve all existing records. If legacy documents already contain
    # identical content, fingerprint only the first one; the remaining
    # NULL values are allowed by PostgreSQL's unique constraint.
    seen_hashes: set[str] = set()
    rows = connection.execute(
        sa.select(documents.c.id, documents.c.content).order_by(documents.c.id)
    )
    for document_id, content in rows:
        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if fingerprint in seen_hashes:
            continue

        connection.execute(
            documents.update()
            .where(documents.c.id == document_id)
            .values(content_sha256=fingerprint)
        )
        seen_hashes.add(fingerprint)

    op.create_unique_constraint(
        "uq_documents_content_sha256",
        "documents",
        ["content_sha256"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_content_sha256",
        "documents",
        type_="unique",
    )
    op.drop_column("documents", "content_sha256")
