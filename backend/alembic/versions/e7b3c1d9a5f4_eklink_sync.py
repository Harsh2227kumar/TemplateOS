"""EkLink sync: sync_state, is_demo flags, approver mirror columns, demo codes

Revision ID: e7b3c1d9a5f4
Revises: d5e1a7c3b9f2
Create Date: 2026-11-09 00:00:00.000000

SYNC_CONTRACT.md sections 6 and 8. Purely additive for existing data:

- sync_state (new): one row remembering the last EkLink change event applied.
- users / organizations / institutes / departments: + is_demo (default false).
- approver_assignments: + eklink_id (EkLink's job id, unique, NULL for local
  rows) and source ('local' | 'eklink', default 'local').

Data (only rows that match exactly; safe on any database):
- the demo organization "TemplateOS Demo Institute" (no code yet) gets code
  DEMO, its institute (code MAIN) becomes DEMO-INST "TemplateOS Demo
  Institute", its departments "Computer Science" / "Academic Affairs" get
  CS / ACAD; all of them and the local users of that organization (no
  eklink_sub) are marked is_demo.

No row is deleted. downgrade() restores the old codes and removes only what
this revision added. Plain ADD / DROP COLUMN (no batch rebuild), so the
lower(name) expression indexes of the directory tables survive on SQLite.
"""

import sqlalchemy as sa
from alembic import op

revision = "e7b3c1d9a5f4"
down_revision = "d5e1a7c3b9f2"
branch_labels = None
depends_on = None

DEMO_ORG_NAME = "TemplateOS Demo Institute"
DIRECTORY_TABLES = ("organizations", "institutes", "departments")


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_event_id", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_pull_at", sa.DateTime(), nullable=True),
        sa.Column("last_push_at", sa.DateTime(), nullable=True),
        sa.Column("last_full_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=True),
        # Event data whose codes did not resolve yet (retried on later batches).
        sa.Column("pending", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    for table in ("users",) + DIRECTORY_TABLES:
        op.add_column(
            table, sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False)
        )

    op.add_column(
        "approver_assignments", sa.Column("eklink_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "approver_assignments",
        sa.Column("source", sa.String(length=10), server_default="local", nullable=False),
    )
    op.create_index(
        "uq_approver_assignments_eklink_id", "approver_assignments", ["eklink_id"], unique=True
    )

    # ── data: the demo directory gets the codes EkLink uses (contract §8) ──
    bind = op.get_bind()
    org_id = bind.execute(
        sa.text(
            "SELECT id FROM organizations WHERE lower(name) = lower(:name) AND code IS NULL"
        ),
        {"name": DEMO_ORG_NAME},
    ).scalar()
    taken = bind.execute(
        sa.text("SELECT count(*) FROM organizations WHERE upper(code) = 'DEMO'")
    ).scalar()
    if org_id is None or taken:
        return
    bind.execute(
        sa.text("UPDATE organizations SET code = 'DEMO', is_demo = :t WHERE id = :id"),
        {"id": org_id, "t": True},
    )
    institutes = bind.execute(
        sa.text("SELECT id, code FROM institutes WHERE organization_id = :id ORDER BY id"),
        {"id": org_id},
    ).fetchall()
    main = [row[0] for row in institutes if row[1] == "MAIN"]
    institute_id = main[0] if main else (institutes[0][0] if len(institutes) == 1 else None)
    if institute_id is not None:
        bind.execute(
            sa.text(
                "UPDATE institutes SET code = 'DEMO-INST', name = :name, is_demo = :t "
                "WHERE id = :id"
            ),
            {"id": institute_id, "name": DEMO_ORG_NAME, "t": True},
        )
        for name, code in (("computer science", "CS"), ("academic affairs", "ACAD")):
            bind.execute(
                sa.text(
                    "UPDATE departments SET code = :code, is_demo = :t "
                    "WHERE institute_id = :inst AND lower(name) = :name AND code IS NULL"
                ),
                {"code": code, "inst": institute_id, "name": name, "t": True},
            )
    bind.execute(
        sa.text(
            "UPDATE users SET is_demo = :t "
            "WHERE organization_id = :id AND eklink_sub IS NULL"
        ),
        {"id": org_id, "t": True},
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Give the demo rows back the codes they had before this revision.
    bind.execute(
        sa.text("UPDATE departments SET code = NULL WHERE is_demo = :t AND code IN ('CS', 'ACAD')"),
        {"t": True},
    )
    bind.execute(
        sa.text("UPDATE institutes SET code = 'MAIN' WHERE is_demo = :t AND code = 'DEMO-INST'"),
        {"t": True},
    )
    bind.execute(
        sa.text("UPDATE organizations SET code = NULL WHERE is_demo = :t AND code = 'DEMO'"),
        {"t": True},
    )

    op.drop_index("uq_approver_assignments_eklink_id", table_name="approver_assignments")
    op.drop_column("approver_assignments", "source")
    op.drop_column("approver_assignments", "eklink_id")
    for table in DIRECTORY_TABLES + ("users",):
        op.drop_column(table, "is_demo")
    op.drop_table("sync_state")
