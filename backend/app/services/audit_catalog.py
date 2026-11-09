"""
The audit action catalog (V1.7 Phase 3): every action an audit row may
carry, with the label and area the admin Audit Log page filters by
(served by GET /admin/audit-logs/actions, so the frontend never hard-codes
labels). Unknown actions are rejected when written.
"""

AUDIT_AREAS = ("templates", "documents", "editor", "ai", "admin", "auth")

# action -> (label, area)
AUDIT_ACTIONS: dict[str, tuple[str, str]] = {
    # Templates
    "template.upload": ("Template uploaded", "templates"),
    "template.access_update": ("Template access changed", "templates"),
    "template.delete": ("Template deleted", "templates"),
    "template.placeholders_detect": ("Placeholders detected", "templates"),
    "template.placeholders_fix": ("Placeholders fixed", "templates"),
    "template.clean": ("Template cleaned", "templates"),
    "template.fields_update": ("Template fields updated", "templates"),
    "template.customize": ("Personal copy created", "templates"),
    "template.file_edit": ("Template file edited", "templates"),
    "template.revision_restore": ("Template revision restored", "templates"),
    # Documents
    "document.create": ("Draft created", "documents"),
    "document.values_update": ("Draft values saved", "documents"),
    "document.generate": ("Document generated", "documents"),
    "document.pdf_retry": ("PDF conversion retried", "documents"),
    "document.version_restore": ("Version restored", "documents"),
    "document.download": ("Document downloaded", "documents"),
    "document.download_denied": ("Download denied", "documents"),
    "document.file_edit": ("Document file edited", "documents"),
    # Word file editor (V1.7 P2.1)
    "editor.session_open": ("Editor opened", "editor"),
    "editor.save_failed": ("Editor save failed", "editor"),
    # AI
    "ai.improve_text": ("AI text improvement", "ai"),
    "ai.suggest_fields": ("AI field suggestions", "ai"),
    # Admin
    "admin.user_update": ("User updated", "admin"),
    "admin.organization_create": ("Organization created", "admin"),
    "admin.organization_update": ("Organization updated", "admin"),
    "admin.organization_delete": ("Organization deleted", "admin"),
    "admin.department_create": ("Department created", "admin"),
    "admin.department_update": ("Department updated", "admin"),
    "admin.department_delete": ("Department deleted", "admin"),
    "admin.institute_create": ("Institute created", "admin"),
    "admin.institute_update": ("Institute updated", "admin"),
    "admin.institute_delete": ("Institute deleted", "admin"),
    "admin.user_deactivate": ("User deactivated", "admin"),
    "admin.user_reactivate": ("User reactivated", "admin"),
    "admin.approver_assign": ("Approver assigned", "admin"),
    "admin.approver_end": ("Approver assignment ended", "admin"),
    "admin.audit_export": ("Audit log exported", "admin"),
    "admin.eklink_sync": ("EkLink sync run", "admin"),
    "admin.eklink_full_resync": ("EkLink full resync", "admin"),
    # Auth
    "auth.login": ("Signed in", "auth"),
    "auth.logout": ("Signed out", "auth"),
    "auth.login_failed": ("Failed sign-in", "auth"),
}

ENTITY_TYPES = (
    "template",
    "template_revision",
    "document",
    "document_version",
    "editor_session",
    "user",
    "organization",
    "institute",
    "department",
    "approver_assignment",
    "audit_log",
    "sync",
)


def is_known_action(action: str) -> bool:
    return action in AUDIT_ACTIONS


def action_options() -> list[dict[str, str]]:
    """[{action, label, area}] in catalog order (grouped by area)."""
    return [{"action": action, "label": label, "area": area} for action, (label, area) in AUDIT_ACTIONS.items()]
