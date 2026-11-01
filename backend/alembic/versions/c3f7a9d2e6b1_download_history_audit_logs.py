"""download history and audit logs

Revision ID: c3f7a9d2e6b1
Revises: b8e4c2a6d1f9
Create Date: 2026-11-01 00:00:00.000000

V1.7 Phase 3 (download history + audit).

download_history (new): one row per successful DOCX/PDF download
- user_id / document_id / version_id -> SET NULL, so history outlives its
  subjects; version, version_source (generated | manual_edit),
  document_name and file_name are snapshots
- format CHECK in ('docx', 'pdf'), file_size, ip_address, user_agent,
  downloaded_at
- indexes (user_id, downloaded_at), (document_id, downloaded_at)

audit_logs (new): append-only trail of important actions
- actor_id -> users SET NULL (+ actor_email snapshot), action (indexed),
  entity_type / entity_id (indexed together), organization_id /
  department_id -> SET NULL (indexed: admin scoping), summary, details
  (JSON text, no secrets or content), ip_address, created_at (indexed)
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c3f7a9d2e6b1"
down_revision = "b8e4c2a6d1f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("version_source", sa.String(length=20), nullable=True),
        sa.Column("format", sa.String(length=4), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column(
            "downloaded_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("format IN ('docx', 'pdf')", name="ck_download_history_format"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_download_history_user_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_download_history_document_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            name="fk_download_history_version_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_download_history_user_downloaded", "download_history", ["user_id", "downloaded_at"], unique=False
    )
    op.create_index(
        "ix_download_history_document_downloaded",
        "download_history",
        ["document_id", "downloaded_at"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_audit_logs_actor_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_audit_logs_organization_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_audit_logs_department_id", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"], unique=False)
    op.create_index("ix_audit_logs_department_id", "audit_logs", ["department_id"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_department_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_download_history_document_downloaded", table_name="download_history")
    op.drop_index("ix_download_history_user_downloaded", table_name="download_history")
    op.drop_table("download_history")
