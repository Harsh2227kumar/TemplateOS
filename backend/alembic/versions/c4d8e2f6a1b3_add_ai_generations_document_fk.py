"""add_ai_generations_document_fk

Revision ID: c4d8e2f6a1b3
Revises: 9a8b7c6d5e4f
Create Date: 2026-10-12 00:00:00.000000

V1.5 Phase 1 — Member 3: link ai_generations.document_id to the V1.4
documents table. V1.3 created the column as a plain nullable Integer
because documents did not exist yet.

- ai_generations.document_id -> documents.id ON DELETE SET NULL: like
  template_id, the audit row survives deletion of the draft.
- Any existing document_id that points at no document is set to NULL
  first, otherwise adding the constraint would fail on PostgreSQL.
- batch_alter_table so the same migration runs on SQLite (tests), which
  cannot ALTER TABLE ... ADD CONSTRAINT.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c4d8e2f6a1b3"
down_revision = "9a8b7c6d5e4f"
branch_labels = None
depends_on = None

FK_NAME = "fk_ai_generations_document_id_documents"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ai_generations SET document_id = NULL "
            "WHERE document_id IS NOT NULL "
            "AND document_id NOT IN (SELECT id FROM documents)"
        )
    )
    with op.batch_alter_table("ai_generations") as batch_op:
        batch_op.create_foreign_key(
            FK_NAME,
            "documents",
            ["document_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_generations") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
