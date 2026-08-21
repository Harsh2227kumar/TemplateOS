from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.models.template import Template
from app.schemas.template import TemplateCreate

def create_template(db: Session, data: TemplateCreate) -> Template:
    """
    Insert a new template row.
    data.original_file_path must be a relative string path, never binary.
    """
    db_obj = Template(**data.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_template_by_id(db: Session, template_id: int) -> Template | None:
    """Return Template or None."""
    result = db.execute(select(Template).where(Template.id == template_id))
    return result.scalar_one_or_none()

def get_templates_by_user(db: Session, user_id: int) -> list[Template]:
    """Return all templates uploaded by the given user, newest first."""
    result = db.execute(
        select(Template)
        .where(Template.uploaded_by == user_id)
        .order_by(Template.created_at.desc())
    )
    return list(result.scalars().all())

def get_public_templates(db: Session, limit: int = 50, offset: int = 0) -> list[Template]:
    """
    Return publicly visible templates, newest first.
    Used by the template library listing in Phase 3.
    """
    result = db.execute(
        select(Template)
        .where(Template.visibility == "public")
        .where(Template.status.in_(["active", "uploaded", "field_configured"]))
        .order_by(Template.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())

def get_templates_by_category(
    db: Session,
    category: str,
    user_id: int | None = None,
    limit: int = 50,
) -> list[Template]:
    """
    Return templates filtered by category.
    If user_id is provided, returns only that user's templates in the category.
    """
    query = select(Template).where(Template.category == category)
    if user_id is not None:
        query = query.where(Template.uploaded_by == user_id)
    query = query.order_by(Template.created_at.desc()).limit(limit)
    result = db.execute(query)
    return list(result.scalars().all())


def get_library_templates(
    db: Session,
    user_id: int,
    search: str | None = None,
    category: str | None = None,
    visibility: str | None = None,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Template], int]:
    """
    Return templates visible to the given user.

    Visibility rules for V1.2:
    - Always include user's own templates (any visibility)
    - Always include public templates from other users
    - Do NOT include other users' private/org/department/group templates
      (organization and group-based visibility is deferred to V1.9)

    Supports:
    - Search: case-insensitive partial match on template name
    - Category filter: exact match
    - Visibility filter: exact match
    - Status filter: exact match
    - Pagination: page + limit based

    Returns: (list_of_templates, total_count)
    """
    visibility_filter = or_(
        Template.uploaded_by == user_id,
        Template.visibility == "public",
    )

    query = select(Template).where(visibility_filter)

    if search:
        query = query.where(Template.name.ilike(f"%{search}%"))
    if category:
        query = query.where(Template.category == category)
    if visibility:
        query = query.where(Template.visibility == visibility)
    if status:
        query = query.where(Template.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    offset = (page - 1) * limit
    query = query.order_by(Template.created_at.desc()).offset(offset).limit(limit)

    result = db.execute(query)
    templates = list(result.scalars().all())
    return templates, total


def get_template_count_by_user(db: Session, user_id: int) -> int:
    """Return the total number of templates uploaded by a user."""
    result = db.execute(
        select(func.count(Template.id)).where(Template.uploaded_by == user_id)
    )
    return result.scalar() or 0


def search_templates(
    db: Session,
    query_text: str,
    user_id: int | None = None,
    limit: int = 20,
) -> list[Template]:
    """
    Search templates by name (case-insensitive partial match).
    If user_id is provided, only searches that user's templates.
    Otherwise searches all public templates.
    """
    base = select(Template)
    if user_id is not None:
        base = base.where(Template.uploaded_by == user_id)
    else:
        base = base.where(Template.visibility == "public")
    base = base.where(Template.name.ilike(f"%{query_text}%"))
    base = base.order_by(Template.created_at.desc()).limit(limit)
    result = db.execute(base)
    return list(result.scalars().all())
