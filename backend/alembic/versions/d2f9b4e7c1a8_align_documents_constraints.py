"""align_documents_constraints

Revision ID: d2f9b4e7c1a8
Revises: c4d8e2f6a1b3
Create Date: 2026-10-12 00:00:00.000000

Repair schema drift on databases whose documents / document_values tables
were created by an uncommitted migration (f3713a976f21) instead of
9a8b7c6d5e4f. That version had:

- documents.template_id -> templates.id ON DELETE RESTRICT (expected CASCADE)
- documents.created_by -> users.id with no ON DELETE (expected CASCADE)
- no uq_document_value_key UNIQUE (document_id, field_name)
- documents.status VARCHAR(30) (expected 50)

Every step inspects the live schema first and only changes what differs,
so on a database built from this repo's migrations this is a no-op.

Recovery for an affected database (its alembic_version is f3713a976f21):
    alembic stamp 9a8b7c6d5e4f   # the documents tables already exist
    alembic upgrade head          # c4d8e2f6a1b3 + this repair

downgrade() is intentionally a no-op: the drifted state is not a valid
target to restore.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "d2f9b4e7c1a8"
down_revision = "c4d8e2f6a1b3"
branch_labels = None
depends_on = None

_EXPECTED_DOCUMENT_FKS = {
    # column: (fk name, referred table)
    "template_id": ("documents_template_id_fkey", "templates"),
    "created_by": ("documents_created_by_fkey", "users"),
}


# SQLite reflects FKs without their names; in batch (table-rebuild) mode this
# convention names them so they can be dropped. PostgreSQL returns real names.
_BATCH_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _ondelete(fk: dict) -> str:
    return (fk.get("options", {}).get("ondelete") or "").upper()


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # 1. documents FKs must CASCADE.
    wrong_fks = [
        fk
        for fk in inspector.get_foreign_keys("documents")
        if fk["constrained_columns"] and fk["constrained_columns"][0] in _EXPECTED_DOCUMENT_FKS
        and _ondelete(fk) != "CASCADE"
    ]
    status_column = next(
        c for c in inspector.get_columns("documents") if c["name"] == "status"
    )
    status_too_short = (getattr(status_column["type"], "length", None) or 0) < 50

    if wrong_fks or status_too_short:
        with op.batch_alter_table("documents", naming_convention=_BATCH_NAMING) as batch_op:
            for fk in wrong_fks:
                column = fk["constrained_columns"][0]
                name, referred = _EXPECTED_DOCUMENT_FKS[column]
                existing = fk["name"] or f"fk_documents_{column}_{fk['referred_table']}"
                batch_op.drop_constraint(existing, type_="foreignkey")
                batch_op.create_foreign_key(
                    name, referred, [column], ["id"], ondelete="CASCADE"
                )
            if status_too_short:
                batch_op.alter_column(
                    "status",
                    existing_type=status_column["type"],
                    type_=sa.String(length=50),
                    existing_nullable=False,
                )

    # 2. One value per field per document.
    has_unique = any(
        set(uc["column_names"]) == {"document_id", "field_name"}
        for uc in inspector.get_unique_constraints("document_values")
    )
    if not has_unique:
        with op.batch_alter_table("document_values") as batch_op:
            batch_op.create_unique_constraint(
                "uq_document_value_key", ["document_id", "field_name"]
            )


def downgrade() -> None:
    # Nothing to undo: on a clean database upgrade() changed nothing, and the
    # drifted schema is not a state worth restoring.
    pass
