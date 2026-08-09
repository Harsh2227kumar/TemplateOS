from sqlalchemy import select
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
