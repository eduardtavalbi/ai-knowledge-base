"""add source metadata to document chunks

Revision ID: 4f8b2a1c9d30
Revises: d1a4c8e92f10
Create Date: 2026-11-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "4f8b2a1c9d30"
down_revision: Union[str, Sequence[str], None] = "d1a4c8e92f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("source_page", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("source_section", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "source_section")
    op.drop_column("document_chunks", "source_page")
