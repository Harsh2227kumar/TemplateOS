"""add_organizations_departments

Revision ID: c7a1d3e5f9b2
Revises: f1b7c3d9e2a4
Create Date: 2026-10-13 12:00:00.000000

Real organization / department tables (app/models/organization.py):

- organizations  id PK, name VARCHAR(255) NOT NULL, created_at
                 unique index uq_organizations_name_lower ON lower(name)
- departments    id PK, organization_id -> organizations.id ON DELETE CASCADE,
                 name VARCHAR(255) NOT NULL, created_at
                 unique index uq_departments_org_name_lower
                 ON (organization_id, lower(name))
- users.organization_id / users.department_id            FK, ON DELETE SET NULL
- templates.scope_organization_id / scope_department_id   FK, ON DELETE SET NULL

Backfill (pure Python over the rows, so it behaves the same on PostgreSQL and
SQLite):

1. Organizations come from users.organization and templates.scope_organization.
   Values are trimmed and internal whitespace is collapsed; blank -> ignored.
   Values that are equal case-insensitively become ONE organization, named
   with the most common spelling (ties: the alphabetically first spelling).
2. Departments come from the (organization, department) pairs on users
   (organization, department) and templates (scope_organization,
   scope_department), deduplicated the same way within each organization.
3. The new FK columns are set from those keys.
4. A department string WITHOUT an organization cannot be placed in any
   organization, so it creates no department and its row keeps
   department_id / scope_department_id NULL ("unlinked"). The legacy string
   is left in place so an admin can see it and assign a real department.

The legacy string columns are NOT modified or dropped: older code keeps
reading them and a downgrade restores exactly the previous state. From this
revision on the application writes them as denormalized copies of the linked
names (see app/services/org_directory.py) and never reads them for access.

batch_alter_table keeps the column/FK changes working on SQLite.
"""

from collections import Counter, defaultdict

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c7a1d3e5f9b2"
down_revision = "f1b7c3d9e2a4"
branch_labels = None
depends_on = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(str(value).split())
    return collapsed or None


def _key(value: str) -> str:
    return value.lower()


def _display_name(counter: Counter) -> str:
    # Most common spelling; ties broken by the alphabetically first spelling.
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_organizations_name_lower",
        "organizations",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_departments_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_departments_organization_id",
        "departments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_departments_org_name_lower",
        "departments",
        ["organization_id", sa.text("lower(name)")],
        unique=True,
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_users_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_users_department_id",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_users_organization_id", ["organization_id"])
        batch_op.create_index("ix_users_department_id", ["department_id"])

    with op.batch_alter_table("templates") as batch_op:
        batch_op.add_column(
            sa.Column("scope_organization_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("scope_department_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_templates_scope_organization_id",
            "organizations",
            ["scope_organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_templates_scope_department_id",
            "departments",
            ["scope_department_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_templates_scope_organization_id", ["scope_organization_id"]
        )
        batch_op.create_index("ix_templates_scope_department_id", ["scope_department_id"])

    _backfill()


def _backfill() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("organization", sa.String),
        sa.column("department", sa.String),
        sa.column("organization_id", sa.Integer),
        sa.column("department_id", sa.Integer),
    )
    templates = sa.table(
        "templates",
        sa.column("id", sa.Integer),
        sa.column("scope_organization", sa.String),
        sa.column("scope_department", sa.String),
        sa.column("scope_organization_id", sa.Integer),
        sa.column("scope_department_id", sa.Integer),
    )
    organizations = sa.table(
        "organizations", sa.column("id", sa.Integer), sa.column("name", sa.String)
    )
    departments = sa.table(
        "departments",
        sa.column("id", sa.Integer),
        sa.column("organization_id", sa.Integer),
        sa.column("name", sa.String),
    )

    # (table, row id, org string, dept string)
    rows: list[tuple[str, int, str | None, str | None]] = []
    for row in bind.execute(
        sa.select(users.c.id, users.c.organization, users.c.department)
    ):
        rows.append(("users", row[0], _clean(row[1]), _clean(row[2])))
    for row in bind.execute(
        sa.select(
            templates.c.id, templates.c.scope_organization, templates.c.scope_department
        )
    ):
        rows.append(("templates", row[0], _clean(row[1]), _clean(row[2])))

    org_spellings: dict[str, Counter] = defaultdict(Counter)
    dept_spellings: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for _table, _id, org, dept in rows:
        if org is None:
            continue
        org_spellings[_key(org)][org] += 1
        if dept is not None:
            dept_spellings[(_key(org), _key(dept))][dept] += 1

    org_ids: dict[str, int] = {}
    for org_key in sorted(org_spellings):
        name = _display_name(org_spellings[org_key])
        bind.execute(sa.insert(organizations).values(name=name))
        org_ids[org_key] = bind.execute(
            sa.select(organizations.c.id).where(organizations.c.name == name)
        ).scalar_one()

    dept_ids: dict[tuple[str, str], int] = {}
    for pair in sorted(dept_spellings):
        name = _display_name(dept_spellings[pair])
        organization_id = org_ids[pair[0]]
        bind.execute(
            sa.insert(departments).values(organization_id=organization_id, name=name)
        )
        dept_ids[pair] = bind.execute(
            sa.select(departments.c.id).where(
                departments.c.organization_id == organization_id,
                departments.c.name == name,
            )
        ).scalar_one()

    for table_name, row_id, org, dept in rows:
        if org is None:
            continue  # department without organization: stays unlinked
        org_id = org_ids[_key(org)]
        dept_id = dept_ids.get((_key(org), _key(dept))) if dept is not None else None
        if table_name == "users":
            bind.execute(
                sa.update(users)
                .where(users.c.id == row_id)
                .values(organization_id=org_id, department_id=dept_id)
            )
        else:
            bind.execute(
                sa.update(templates)
                .where(templates.c.id == row_id)
                .values(scope_organization_id=org_id, scope_department_id=dept_id)
            )


def downgrade() -> None:
    with op.batch_alter_table("templates") as batch_op:
        batch_op.drop_index("ix_templates_scope_department_id")
        batch_op.drop_index("ix_templates_scope_organization_id")
        batch_op.drop_constraint("fk_templates_scope_department_id", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_templates_scope_organization_id", type_="foreignkey"
        )
        batch_op.drop_column("scope_department_id")
        batch_op.drop_column("scope_organization_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_department_id")
        batch_op.drop_index("ix_users_organization_id")
        batch_op.drop_constraint("fk_users_department_id", type_="foreignkey")
        batch_op.drop_constraint("fk_users_organization_id", type_="foreignkey")
        batch_op.drop_column("department_id")
        batch_op.drop_column("organization_id")

    op.drop_index("uq_departments_org_name_lower", table_name="departments")
    op.drop_index("ix_departments_organization_id", table_name="departments")
    op.drop_table("departments")
    op.drop_index("uq_organizations_name_lower", table_name="organizations")
    op.drop_table("organizations")
