"""generated_files PDF conversion status

Revision ID: e3c9a7b5d1f2
Revises: d8f2a4c6e1b9
Create Date: 2026-10-15 00:00:00.000000

V1.6 Phase 2: store the PDF conversion state instead of deriving it.

- pdf_status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                    (pending | converted | failed, checked by the model)
- pdf_converted_at  TIMESTAMP NULL
- pdf_attempts      INTEGER NOT NULL DEFAULT 0

pdf_error (VARCHAR(500)) is kept as is.

Backfill of existing rows (no row stays "pending"):
- pdf_path set                    -> converted
- pdf_path NULL, pdf_error set    -> failed (the error is kept)
- pdf_path NULL, pdf_error NULL   -> failed, pdf_error = NOT_SET_UP_ERROR

pdf_attempts stays 0 and pdf_converted_at NULL for old rows: the history of
those conversions was never recorded. The downgrade clears NOT_SET_UP_ERROR
again so the old derived "not_configured" state comes back.

batch_alter_table: works on PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "e3c9a7b5d1f2"
down_revision = "d8f2a4c6e1b9"
branch_labels = None
depends_on = None

NOT_SET_UP_ERROR = "PDF conversion was not set up when this document was generated"


def upgrade() -> None:
    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pdf_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(sa.Column("pdf_converted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("pdf_attempts", sa.Integer(), nullable=False, server_default="0")
        )

    generated_files = sa.table(
        "generated_files",
        sa.column("pdf_path", sa.String),
        sa.column("pdf_error", sa.String),
        sa.column("pdf_status", sa.String),
    )
    op.execute(
        generated_files.update()
        .where(generated_files.c.pdf_path.isnot(None))
        .values(pdf_status="converted")
    )
    op.execute(
        generated_files.update()
        .where(generated_files.c.pdf_path.is_(None))
        .where(generated_files.c.pdf_error.isnot(None))
        .values(pdf_status="failed")
    )
    op.execute(
        generated_files.update()
        .where(generated_files.c.pdf_path.is_(None))
        .where(generated_files.c.pdf_error.is_(None))
        .values(pdf_status="failed", pdf_error=NOT_SET_UP_ERROR)
    )


def downgrade() -> None:
    # Before this revision "no error and no PDF" meant "not configured".
    generated_files = sa.table("generated_files", sa.column("pdf_error", sa.String))
    op.execute(
        generated_files.update()
        .where(generated_files.c.pdf_error == NOT_SET_UP_ERROR)
        .values(pdf_error=None)
    )
    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.drop_column("pdf_attempts")
        batch_op.drop_column("pdf_converted_at")
        batch_op.drop_column("pdf_status")
