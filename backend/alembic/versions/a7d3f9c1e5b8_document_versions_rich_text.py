"""document versions, rich text values and AI flags

Revision ID: a7d3f9c1e5b8
Revises: e3c9a7b5d1f2
Create Date: 2026-10-18 00:00:00.000000

V1.7 Phase 2.

document_values (new columns):
- value_format    VARCHAR(10) NOT NULL DEFAULT 'plain'
                  CHECK value_format IN ('plain', 'rich')
- rich_content    TEXT NULL        validated Tiptap JSON (value_format 'rich')
- ai_modified     BOOLEAN NOT NULL DEFAULT false
- ai_action       VARCHAR(20) NULL grammar | tone | concise | formal | expand
- ai_modified_at  TIMESTAMP NULL

document_versions (new): one row per Generate.
- id, document_id -> documents.id ON DELETE CASCADE (indexed), version,
  created_by -> users.id ON DELETE SET NULL (nullable), created_at,
  template_version, values_snapshot TEXT NOT NULL (JSON array), note
- UNIQUE (document_id, version)  uq_document_versions_document_version

generated_files: one row per version instead of per document.
- drop uq_generated_files_document_id, index document_id instead
- version_id -> document_versions.id ON DELETE CASCADE, NOT NULL,
  UNIQUE (uq_generated_files_version_id)
- files_pruned_at TIMESTAMP NULL (retention removed the files)

Backfill: every existing generated_files row becomes version 1 of its
document (created_by = the document owner, created_at = generated_at,
template_version copied) with a snapshot of the document's current values,
all plain and not AI-modified. Written as SQL per dialect (PostgreSQL
json_agg, SQLite JSON1), so `alembic upgrade --sql` shows it too.

Downgrade: keeps only the newest version's generated_files row per document
(the files of the deleted rows stay on disk), restores the per-document
unique constraint, drops document_versions and the five document_values
columns (rich values keep their plain-text projection in `value`).

batch_alter_table: works on PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "a7d3f9c1e5b8"
down_revision = "e3c9a7b5d1f2"
branch_labels = None
depends_on = None


_SNAPSHOT_POSTGRESQL = """
COALESCE((
    SELECT json_agg(json_build_object(
        'field_name', v.field_name,
        'value', v.value,
        'value_format', 'plain',
        'rich_content', NULL,
        'ai_modified', false,
        'ai_action', NULL
    ) ORDER BY v.field_name)::text
    FROM document_values v
    WHERE v.document_id = gf.document_id
), '[]')
"""

_SNAPSHOT_SQLITE = """
COALESCE((
    SELECT json_group_array(json_object(
        'field_name', v.field_name,
        'value', v.value,
        'value_format', 'plain',
        'rich_content', NULL,
        'ai_modified', json('false'),
        'ai_action', NULL
    ))
    FROM (
        SELECT field_name, value FROM document_values
        WHERE document_id = gf.document_id
        ORDER BY field_name
    ) v
), '[]')
"""


def _snapshot_sql() -> str:
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        return _SNAPSHOT_POSTGRESQL
    if dialect == "sqlite":
        return _SNAPSHOT_SQLITE
    raise NotImplementedError(f"Backfill is not written for the {dialect} dialect")


def upgrade() -> None:
    with op.batch_alter_table("document_values") as batch_op:
        batch_op.add_column(
            sa.Column(
                "value_format",
                sa.String(length=10),
                nullable=False,
                server_default="plain",
            )
        )
        batch_op.add_column(sa.Column("rich_content", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("ai_modified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("ai_action", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("ai_modified_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_document_values_value_format", "value_format IN ('plain', 'rich')"
        )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("values_snapshot", sa.Text(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "version", name="uq_document_versions_document_version"
        ),
    )
    op.create_index(
        op.f("ix_document_versions_id"), "document_versions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_document_versions_document_id"),
        "document_versions",
        ["document_id"],
        unique=False,
    )

    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.drop_constraint("uq_generated_files_document_id", type_="unique")
        batch_op.add_column(sa.Column("version_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("files_pruned_at", sa.DateTime(), nullable=True))
        batch_op.create_index(
            "ix_generated_files_document_id", ["document_id"], unique=False
        )

    op.execute(
        "INSERT INTO document_versions "
        "(document_id, version, created_by, created_at, template_version, values_snapshot) "
        "SELECT gf.document_id, 1, d.created_by, gf.generated_at, gf.template_version, "
        f"{_snapshot_sql()} "
        "FROM generated_files gf LEFT JOIN documents d ON d.id = gf.document_id"
    )
    op.execute(
        "UPDATE generated_files SET version_id = ("
        "SELECT dv.id FROM document_versions dv "
        "WHERE dv.document_id = generated_files.document_id AND dv.version = 1)"
    )

    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.alter_column("version_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint("uq_generated_files_version_id", ["version_id"])
        batch_op.create_foreign_key(
            "fk_generated_files_version_id",
            "document_versions",
            ["version_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    # Keep the newest version's row per document; older rows go away.
    op.execute(
        "DELETE FROM generated_files WHERE version_id NOT IN ("
        "SELECT dv.id FROM document_versions dv "
        "WHERE dv.version = ("
        "SELECT MAX(dv2.version) FROM document_versions dv2 "
        "JOIN generated_files g2 ON g2.version_id = dv2.id "
        "WHERE dv2.document_id = dv.document_id))"
    )

    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.drop_constraint("fk_generated_files_version_id", type_="foreignkey")
        batch_op.drop_constraint("uq_generated_files_version_id", type_="unique")
        batch_op.drop_index("ix_generated_files_document_id")
        batch_op.drop_column("files_pruned_at")
        batch_op.drop_column("version_id")
        batch_op.create_unique_constraint("uq_generated_files_document_id", ["document_id"])

    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_id"), table_name="document_versions")
    op.drop_table("document_versions")

    with op.batch_alter_table("document_values") as batch_op:
        batch_op.drop_constraint("ck_document_values_value_format", type_="check")
        batch_op.drop_column("ai_modified_at")
        batch_op.drop_column("ai_action")
        batch_op.drop_column("ai_modified")
        batch_op.drop_column("rich_content")
        batch_op.drop_column("value_format")
