"""AI fill chat: ai_fill_sessions, ai_fill_messages, template baseline pages

Revision ID: f2a6c8e4b7d1
Revises: e7b3c1d9a5f4
Create Date: 2026-11-11 00:00:00.000000

V1.7 Phase 2.2 (AI fill assistant). Purely additive:

- ai_fill_sessions (new): one chat per document (UNIQUE document_id),
  CASCADE from documents and users.
- ai_fill_messages (new): the chat turns. A user row and the assistant reply
  share `turn`; JSON (answers, proposals, questions) is stored as Text.
  `stage` is the assistant turn's stage (asking | filling | ready).
- templates: + baseline_pages / baseline_pages_version (page count of the
  template rendered with example values, cached per template version; used by
  the fit check after generation).

No backfill. downgrade() drops only what this revision added. Plain ADD /
DROP COLUMN on templates (no batch rebuild).
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a6c8e4b7d1"
down_revision = "e7b3c1d9a5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_fill_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("filled_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'completed')", name="ck_ai_fill_sessions_status"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_ai_fill_sessions_document"),
    )
    op.create_index("ix_ai_fill_sessions_user_id", "ai_fill_sessions", ["user_id"])

    op.create_table(
        "ai_fill_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answers", sa.Text(), nullable=True),
        sa.Column("proposals", sa.Text(), nullable=True),
        sa.Column("questions", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(length=10), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_ai_fill_messages_role"),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('asking', 'filling', 'ready')",
            name="ck_ai_fill_messages_stage",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["ai_fill_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "turn", "role", name="uq_ai_fill_messages_turn_role"),
    )
    op.create_index("ix_ai_fill_messages_session_id", "ai_fill_messages", ["session_id"])

    op.add_column("templates", sa.Column("baseline_pages", sa.Integer(), nullable=True))
    op.add_column("templates", sa.Column("baseline_pages_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "baseline_pages_version")
    op.drop_column("templates", "baseline_pages")
    op.drop_index("ix_ai_fill_messages_session_id", table_name="ai_fill_messages")
    op.drop_table("ai_fill_messages")
    op.drop_index("ix_ai_fill_sessions_user_id", table_name="ai_fill_sessions")
    op.drop_table("ai_fill_sessions")
