"""add persistent user sessions and refresh token rotation

Revision ID: b81d2e6f4a90
Revises: 7c2e9a1b4d60
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b81d2e6f4a90"
down_revision: Union[str, Sequence[str], None] = "7c2e9a1b4d60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_user_sessions_refresh_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])\n    op.create_table(\n        "session_refresh_tokens",\n        sa.Column("id", sa.Integer(), primary_key=True),\n        sa.Column("session_id", sa.Integer(), nullable=False),\n        sa.Column("token_hash", sa.String(length=64), nullable=False),\n        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),\n        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),\n        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.id"], ondelete="CASCADE"),\n        sa.UniqueConstraint("token_hash", name="uq_session_refresh_tokens_token_hash"),\n    )\n    op.create_index("ix_session_refresh_tokens_session_id", "session_refresh_tokens", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_session_refresh_tokens_session_id", table_name="session_refresh_tokens")\n    op.drop_table("session_refresh_tokens")\n    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
