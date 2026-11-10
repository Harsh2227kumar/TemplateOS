"""create_generated_files_table

Revision ID: b6d2e8f4a1c7
Revises: f1b7c3d9e2a4
Create Date: 2026-10-13 12:00:00.000000

V1.6 document generation (app/models/generated_file.py). One row per
document holding the latest generated DOCX (and PDF) paths:

- id                    INTEGER PK
- document_id           INTEGER NOT NULL UNIQUE -> documents.id ON DELETE CASCADE
- docx_path             VARCHAR(500) NOT NULL   relative storage path
- pdf_path              VARCHAR(500) NULL       relative storage path
- pdf_error             VARCHAR(500) NULL       last PDF conversion error
- template_version      INTEGER NULL            template.version snapshot
- template_source_path  VARCHAR(500) NULL       template file rendered from
- generated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP

Plain create_table: works on PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "b6d2e8f4a1c7"
down_revision = "f1b7c3d9e2a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("docx_path", sa.String(length=500), nullable=False),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("pdf_error", sa.String(length=500), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("template_source_path", sa.String(length=500), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_generated_files_document_id"),
    )
    op.create_index(
        op.f("ix_generated_files_id"), "generated_files", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_files_id"), table_name="generated_files")
    op.drop_table("generated_files")
