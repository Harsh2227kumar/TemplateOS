"""merge org tables and generated files heads

Revision ID: d8f2a4c6e1b9
Revises: c7a1d3e5f9b2, b6d2e8f4a1c7
Create Date: 2026-10-13 00:00:00.000000

Wave 2 added two independent migrations on top of f1b7c3d9e2a4:
- c7a1d3e5f9b2: organizations / departments tables + FK columns
- b6d2e8f4a1c7: generated_files table (document generation)

They touch different tables, so this revision only joins the two heads.
"""

# revision identifiers, used by Alembic.
revision = "d8f2a4c6e1b9"
down_revision = ("c7a1d3e5f9b2", "b6d2e8f4a1c7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
