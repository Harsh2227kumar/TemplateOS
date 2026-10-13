"""add_template_access_scopes

Revision ID: a3c7e1f9b2d6
Revises: d2f9b4e7c1a8
Create Date: 2026-10-12 00:00:00.000000

Explicit audience columns on templates (see app/services/template_access.py):

- scope_organization  VARCHAR(255) NULL  organization a template is published to
- scope_department    VARCHAR(255) NULL  department a template is published to
- allowed_roles       TEXT NULL          JSON array of roles; NULL = every role

Backfill: until now org/department scope was inferred from the uploader's
profile, so existing `organization` templates get the uploader's
organization and existing `department` templates get the uploader's
department + organization. Blank values become NULL.

batch_alter_table keeps this working on SQLite as well as PostgreSQL.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "a3c7e1f9b2d6"
down_revision = "d2f9b4e7c1a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("templates") as batch_op:
        batch_op.add_column(
            sa.Column("scope_organization", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("scope_department", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("allowed_roles", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE templates
        SET scope_organization = (
            SELECT NULLIF(TRIM(users.organization), '')
            FROM users WHERE users.id = templates.uploaded_by
        )
        WHERE visibility IN ('organization', 'department')
        """
    )
    op.execute(
        """
        UPDATE templates
        SET scope_department = (
            SELECT NULLIF(TRIM(users.department), '')
            FROM users WHERE users.id = templates.uploaded_by
        )
        WHERE visibility = 'department'
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("templates") as batch_op:
        batch_op.drop_column("allowed_roles")
        batch_op.drop_column("scope_department")
        batch_op.drop_column("scope_organization")
