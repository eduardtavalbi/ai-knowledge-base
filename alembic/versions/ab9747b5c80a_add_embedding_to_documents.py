"""add embedding to documents

Revision ID: ab9747b5c80a
Revises: 932299ee8b87
Create Date: 2026-10-13 15:38:17.045967

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab9747b5c80a'
down_revision: Union[str, Sequence[str], None] = '932299ee8b87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



from pgvector.sqlalchemy import Vector


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("embedding", Vector(384), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "embedding")

    # ### end Alembic commands ###
