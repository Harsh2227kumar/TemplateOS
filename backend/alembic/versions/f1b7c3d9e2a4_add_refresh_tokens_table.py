"""add_refresh_tokens_table

Revision ID: f1b7c3d9e2a4
Revises: a3c7e1f9b2d6
Create Date: 2026-10-13 00:00:00.000000

Cookie sessions with refresh-token rotation (app/crud/refresh_token_crud.py):

- id              INTEGER PK
- user_id         INTEGER NOT NULL -> users.id ON DELETE CASCADE (indexed)
- token_hash      VARCHAR(64) NOT NULL UNIQUE  SHA-256 hex of the opaque token
- family_id       VARCHAR(64) NOT NULL (indexed)  one per login session
- created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
- expires_at      TIMESTAMP NOT NULL
- revoked_at      TIMESTAMP NULL
- replaced_by_id  INTEGER NULL -> refresh_tokens.id ON DELETE SET NULL

Plain create_table/create_index: works on PostgreSQL and SQLite.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "f1b7c3d9e2a4"
down_revision = "a3c7e1f9b2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"),
        "refresh_tokens",
        ["family_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
