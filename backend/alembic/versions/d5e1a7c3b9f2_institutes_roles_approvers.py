"""institutes, user identity fields and approver assignments

Revision ID: d5e1a7c3b9f2
Revises: c3f7a9d2e6b1
Create Date: 2026-11-07 00:00:00.000000

Central-users phase 3. Purely additive for existing data:

- institutes (new): organization -> institute -> department.
- organizations: + code (unique), is_active.
- departments: + institute_id, code, is_active. Name uniqueness moves from
  (organization, lower(name)) to (institute, lower(name)).
- users: + login_id (unique), eklink_sub (unique), member_type, is_active
  (default true), institute_id, batch, section, semester.
- templates: + scope_institute_id ("institute" visibility).
- audit_logs: + institute_id (institute-admin audit scope).
- approver_assignments (new).

Data (generic, safe on any database):
- every existing organization gets one institute (same name, code MAIN) and
  all its departments are attached to it; users / templates / audit rows
  inherit institute_id from their department;
- member_type from role (faculty, student; approver / normal_user -> staff);
- organization / department templates whose scope was never set get the
  uploader's organization / department, so they become visible again.

No row is deleted. downgrade() removes only what this revision added.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e1a7c3b9f2"
down_revision = "c3f7a9d2e6b1"
branch_labels = None
depends_on = None


def _institute_fk_column(name: str, constraint: str) -> sa.Column:
    """Nullable FK to institutes. SQLite cannot add a constraint with ALTER
    TABLE (and does not enforce foreign keys here), so it gets the plain column."""
    if op.get_bind().dialect.name == "sqlite":
        return sa.Column(name, sa.Integer(), nullable=True)
    return sa.Column(
        name,
        sa.Integer(),
        sa.ForeignKey("institutes.id", ondelete="SET NULL", name=constraint),
        nullable=True,
    )


def upgrade() -> None:
    op.create_table(
        "institutes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutes_organization_id", "institutes", ["organization_id"])
    op.create_index(
        "uq_institutes_org_name_lower", "institutes",
        ["organization_id", sa.text("lower(name)")], unique=True,
    )
    op.create_index("uq_institutes_org_code", "institutes", ["organization_id", "code"], unique=True)

    # Plain ADD COLUMN (no table rebuild): on SQLite a batch rebuild would
    # silently drop the lower(name) expression indexes of these tables.
    op.add_column("organizations", sa.Column("code", sa.String(length=32), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("uq_organizations_code", "organizations", ["code"], unique=True)

    op.drop_index("uq_departments_org_name_lower", table_name="departments")
    op.add_column(
        "departments",
        _institute_fk_column("institute_id", "fk_departments_institute_id"),
    )
    op.add_column("departments", sa.Column("code", sa.String(length=32), nullable=True))
    op.add_column(
        "departments",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_departments_institute_id", "departments", ["institute_id"])
    op.create_index(
        "uq_departments_institute_name_lower", "departments",
        ["institute_id", sa.text("lower(name)")], unique=True,
    )
    op.create_index("uq_departments_institute_code", "departments", ["institute_id", "code"], unique=True)

    op.add_column("users", sa.Column("login_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("eklink_sub", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("member_type", sa.String(length=20), nullable=True))
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "users",
        _institute_fk_column("institute_id", "fk_users_institute_id"),
    )
    op.add_column("users", sa.Column("batch", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("section", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("semester", sa.SmallInteger(), nullable=True))
    op.create_index("uq_users_login_id", "users", ["login_id"], unique=True)
    op.create_index("uq_users_eklink_sub", "users", ["eklink_sub"], unique=True)
    op.create_index("ix_users_institute_id", "users", ["institute_id"])

    op.add_column(
        "templates",
        _institute_fk_column("scope_institute_id", "fk_templates_scope_institute_id"),
    )
    op.create_index("ix_templates_scope_institute_id", "templates", ["scope_institute_id"])

    op.add_column(
        "audit_logs",
        _institute_fk_column("institute_id", "fk_audit_logs_institute_id"),
    )
    op.create_index("ix_audit_logs_institute_id", "audit_logs", ["institute_id"])

    op.create_table(
        "approver_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("scope_level", sa.String(length=20), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("institute_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("scope_key", sa.String(length=64), nullable=True),
        sa.Column("valid_from", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["institute_id"], ["institutes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "organization_id", "institute_id", "department_id"):
        op.create_index(f"ix_approver_assignments_{column}", "approver_assignments", [column])

    # ── data ──
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO institutes (organization_id, name, code) "
        "SELECT id, name, 'MAIN' FROM organizations"
    ))
    bind.execute(sa.text(
        "UPDATE departments SET institute_id = "
        "(SELECT i.id FROM institutes i WHERE i.organization_id = departments.organization_id)"
    ))
    bind.execute(sa.text(
        "UPDATE users SET institute_id = "
        "(SELECT d.institute_id FROM departments d WHERE d.id = users.department_id) "
        "WHERE department_id IS NOT NULL"
    ))
    bind.execute(sa.text(
        "UPDATE audit_logs SET institute_id = "
        "(SELECT d.institute_id FROM departments d WHERE d.id = audit_logs.department_id) "
        "WHERE department_id IS NOT NULL"
    ))
    bind.execute(sa.text(
        "UPDATE users SET member_type = CASE role "
        "WHEN 'faculty' THEN 'faculty' WHEN 'student' THEN 'student' "
        "WHEN 'approver' THEN 'staff' WHEN 'normal_user' THEN 'staff' END"
    ))
    # Scoped templates that never got a scope: use the uploader's membership.
    bind.execute(sa.text(
        "UPDATE templates SET "
        "scope_organization_id = (SELECT u.organization_id FROM users u WHERE u.id = templates.uploaded_by), "
        "scope_organization = (SELECT o.name FROM users u JOIN organizations o ON o.id = u.organization_id "
        "                      WHERE u.id = templates.uploaded_by) "
        "WHERE visibility = 'organization' AND scope_organization_id IS NULL"
    ))
    bind.execute(sa.text(
        "UPDATE templates SET "
        "scope_department_id = (SELECT u.department_id FROM users u WHERE u.id = templates.uploaded_by), "
        "scope_organization_id = (SELECT u.organization_id FROM users u WHERE u.id = templates.uploaded_by), "
        "scope_department = (SELECT d.name FROM users u JOIN departments d ON d.id = u.department_id "
        "                    WHERE u.id = templates.uploaded_by), "
        "scope_organization = (SELECT o.name FROM users u JOIN organizations o ON o.id = u.organization_id "
        "                      WHERE u.id = templates.uploaded_by) "
        "WHERE visibility = 'department' AND scope_department_id IS NULL "
        "AND (SELECT u.department_id FROM users u WHERE u.id = templates.uploaded_by) IS NOT NULL"
    ))
    bind.execute(sa.text(
        "UPDATE templates SET scope_institute_id = "
        "(SELECT d.institute_id FROM departments d WHERE d.id = templates.scope_department_id) "
        "WHERE scope_department_id IS NOT NULL"
    ))


def downgrade() -> None:
    for column in ("user_id", "organization_id", "institute_id", "department_id"):
        op.drop_index(f"ix_approver_assignments_{column}", table_name="approver_assignments")
    op.drop_table("approver_assignments")

    op.drop_index("ix_audit_logs_institute_id", table_name="audit_logs")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_column("institute_id")

    op.drop_index("ix_templates_scope_institute_id", table_name="templates")
    with op.batch_alter_table("templates") as batch:
        batch.drop_column("scope_institute_id")

    op.drop_index("ix_users_institute_id", table_name="users")
    op.drop_index("uq_users_eklink_sub", table_name="users")
    op.drop_index("uq_users_login_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        for column in ("semester", "section", "batch", "institute_id", "is_active",
                       "member_type", "eklink_sub", "login_id"):
            batch.drop_column(column)

    op.drop_index("uq_departments_institute_code", table_name="departments")
    op.drop_index("uq_departments_institute_name_lower", table_name="departments")
    op.drop_index("ix_departments_institute_id", table_name="departments")
    with op.batch_alter_table("departments") as batch:
        for column in ("is_active", "code", "institute_id"):
            batch.drop_column(column)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_departments_org_name_lower "
        "ON departments (organization_id, lower(name))"
    )

    op.drop_index("uq_organizations_code", table_name="organizations")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("is_active")
        batch.drop_column("code")
    # A SQLite batch rebuild drops expression indexes; restore it if needed.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_name_lower ON organizations (lower(name))"
    )

    op.drop_index("uq_institutes_org_code", table_name="institutes")
    op.drop_index("uq_institutes_org_name_lower", table_name="institutes")
    op.drop_index("ix_institutes_organization_id", table_name="institutes")
    op.drop_table("institutes")
