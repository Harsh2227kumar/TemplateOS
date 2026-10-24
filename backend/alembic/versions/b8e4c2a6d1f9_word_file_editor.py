"""word file editor: template revisions, personal copies, manual-edit versions, editor sessions

Revision ID: b8e4c2a6d1f9
Revises: a7d3f9c1e5b8
Create Date: 2026-10-19 00:00:00.000000

V1.7 Phase 2.1 (edit Word files in ONLYOFFICE Docs).

templates (new column):
- parent_template_id  INTEGER NULL -> templates.id ON DELETE SET NULL (indexed):
  set on a user's personal copy ("Customize for me")

template_revisions (new): every file change of a template
- id, template_id -> templates ON DELETE CASCADE (indexed), revision
  (UNIQUE per template), source (upload | clean | fix_placeholders |
  customize | manual_edit | restore), file_path, created_by -> users
  ON DELETE SET NULL, created_at, placeholders_added / placeholders_removed
  (JSON text), blank_suggestions, note

document_versions (new columns):
- source           VARCHAR(20) NOT NULL DEFAULT 'generated' (generated | manual_edit)
- base_version_id  -> document_versions ON DELETE SET NULL: the version a
                   manual edit started from

editor_sessions (new): one ONLYOFFICE editing session
- session_key (UNIQUE, the ONLYOFFICE document.key), target_type
  (template | document), template_id / document_id (CASCADE), base_version_id
  (SET NULL), source_path, user_id (CASCADE), status (open | saving | saved |
  closed | failed | expired), result_revision, result_version, error,
  created_at, updated_at, expires_at

Backfill: one 'upload' revision per template that has a file (revision =
templates.version, file = processed copy, else the original upload,
created_by = uploader).

batch_alter_table: works on PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "b8e4c2a6d1f9"
down_revision = "a7d3f9c1e5b8"
branch_labels = None
depends_on = None

REVISION_SOURCES = "('upload', 'clean', 'fix_placeholders', 'customize', 'manual_edit', 'restore')"


def upgrade() -> None:
    with op.batch_alter_table("templates") as batch_op:
        batch_op.add_column(sa.Column("parent_template_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_templates_parent_template_id", ["parent_template_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_templates_parent_template_id",
            "templates",
            ["parent_template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "template_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("placeholders_added", sa.Text(), nullable=True),
        sa.Column("placeholders_removed", sa.Text(), nullable=True),
        sa.Column("blank_suggestions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "revision", name="uq_template_revisions_template_revision"),
        sa.CheckConstraint(f"source IN {REVISION_SOURCES}", name="ck_template_revisions_source"),
    )
    op.create_index(op.f("ix_template_revisions_id"), "template_revisions", ["id"], unique=False)
    op.create_index(
        op.f("ix_template_revisions_template_id"), "template_revisions", ["template_id"], unique=False
    )

    with op.batch_alter_table("document_versions") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=20), nullable=False, server_default="generated")
        )
        batch_op.add_column(sa.Column("base_version_id", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_document_versions_source", "source IN ('generated', 'manual_edit')"
        )
        batch_op.create_foreign_key(
            "fk_document_versions_base_version_id",
            "document_versions",
            ["base_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "editor_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_key", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=10), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["document_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key", name="uq_editor_sessions_session_key"),
        sa.CheckConstraint("target_type IN ('template', 'document')", name="ck_editor_sessions_target_type"),
        sa.CheckConstraint(
            "status IN ('open', 'saving', 'saved', 'closed', 'failed', 'expired')",
            name="ck_editor_sessions_status",
        ),
        sa.CheckConstraint(
            "(target_type = 'template' AND template_id IS NOT NULL AND document_id IS NULL) OR "
            "(target_type = 'document' AND document_id IS NOT NULL AND template_id IS NULL)",
            name="ck_editor_sessions_target",
        ),
    )
    op.create_index(op.f("ix_editor_sessions_id"), "editor_sessions", ["id"], unique=False)
    op.create_index(
        "ix_editor_sessions_target",
        "editor_sessions",
        ["target_type", "template_id", "document_id", "status"],
        unique=False,
    )

    op.execute(
        "INSERT INTO template_revisions "
        "(template_id, revision, source, file_path, created_by, created_at, blank_suggestions) "
        "SELECT t.id, COALESCE(t.version, 1), 'upload', "
        "COALESCE(t.processed_file_path, t.original_file_path), t.uploaded_by, "
        "COALESCE(t.updated_at, t.created_at, CURRENT_TIMESTAMP), 0 "
        "FROM templates t "
        "WHERE COALESCE(t.processed_file_path, t.original_file_path) IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_editor_sessions_target", table_name="editor_sessions")
    op.drop_index(op.f("ix_editor_sessions_id"), table_name="editor_sessions")
    op.drop_table("editor_sessions")

    with op.batch_alter_table("document_versions") as batch_op:
        batch_op.drop_constraint("fk_document_versions_base_version_id", type_="foreignkey")
        batch_op.drop_constraint("ck_document_versions_source", type_="check")
        batch_op.drop_column("base_version_id")
        batch_op.drop_column("source")

    op.drop_index(op.f("ix_template_revisions_template_id"), table_name="template_revisions")
    op.drop_index(op.f("ix_template_revisions_id"), table_name="template_revisions")
    op.drop_table("template_revisions")

    with op.batch_alter_table("templates") as batch_op:
        batch_op.drop_constraint("fk_templates_parent_template_id", type_="foreignkey")
        batch_op.drop_index("ix_templates_parent_template_id")
        batch_op.drop_column("parent_template_id")
