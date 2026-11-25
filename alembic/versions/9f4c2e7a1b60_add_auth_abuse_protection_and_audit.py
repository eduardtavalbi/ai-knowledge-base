"""add database-backed auth rate limits and security audit events

Revision ID: 9f4c2e7a1b60
Revises: c3a9f1d7e602
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9f4c2e7a1b60"
down_revision: Union[str, Sequence[str], None] = "c3a9f1d7e602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key_hash", sa.String(length=64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_rate_limit_buckets_window_started_at", "rate_limit_buckets", ["window_started_at"])
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_security_audit_events_created_at",
        "security_audit_events",
        ["created_at"],
    )
    op.create_index(
        "ix_security_audit_events_event_type_created_at",
        "security_audit_events",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_audit_events_event_type_created_at", table_name="security_audit_events")
    op.drop_index("ix_security_audit_events_created_at", table_name="security_audit_events")
    op.drop_table("security_audit_events")
    op.drop_index("ix_rate_limit_buckets_window_started_at", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
