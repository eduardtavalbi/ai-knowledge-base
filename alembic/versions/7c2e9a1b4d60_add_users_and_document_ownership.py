"""add users and per-user document ownership

Revision ID: 7c2e9a1b4d60
Revises: 4f8b2a1c9d30
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pwdlib import PasswordHash

from app.core.config import settings


revision: str = "7c2e9a1b4d60"
down_revision: Union[str, Sequence[str], None] = "4f8b2a1c9d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.add_column("documents", sa.Column("user_id", sa.Integer(), nullable=True))
    connection = op.get_bind()
    document_count = connection.execute(
        sa.text("SELECT count(*) FROM documents")
    ).scalar_one()

    if document_count:
        email = settings.migration_owner_email.strip().casefold()
        password = settings.migration_owner_password
        if not email or len(password) < 12:
            raise RuntimeError(
                "Existing documents need an owner. Set MIGRATION_OWNER_EMAIL "
                "and MIGRATION_OWNER_PASSWORD (at least 12 characters) before "
                "running this migration."
            )
        hashed_password = PasswordHash.recommended().hash(password)
        user_id = connection.execute(
            sa.text(
                "INSERT INTO users (email, hashed_password) "
                "VALUES (:email, :hashed_password) RETURNING id"
            ),
            {"email": email, "hashed_password": hashed_password},
        ).scalar_one()
        connection.execute(
            sa.text("UPDATE documents SET user_id = :user_id"),
            {"user_id": user_id},
        )

    op.alter_column("documents", "user_id", nullable=False)
    op.drop_constraint("uq_documents_content_sha256", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_user_content_sha256",
        "documents",
        ["user_id", "content_sha256"],
    )
    op.create_foreign_key(
        "fk_documents_user_id_users",
        "documents",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_constraint("fk_documents_user_id_users", "documents", type_="foreignkey")
    op.drop_constraint(
        "uq_documents_user_content_sha256",
        "documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_documents_content_sha256",
        "documents",
        ["content_sha256"],
    )
    op.drop_column("documents", "user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
