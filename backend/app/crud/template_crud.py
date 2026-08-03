from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.schemas.template import TemplateCreate

async def create_template(db: AsyncSession, data: TemplateCreate) -> Template:
    """
    Insert a new template row.
    data.original_file_path must be a relative string path, never binary.
    """
    db_obj = Template(**data.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

async def get_template_by_id(db: AsyncSession, template_id: int) -> Template | None:
    """Return Template or None."""
    result = await db.execute(select(Template).where(Template.id == template_id))
    return result.scalar_one_or_none()

async def get_templates_by_user(db: AsyncSession, user_id: int) -> list[Template]:
    """Return all templates uploaded by the given user, newest first."""
    result = await db.execute(
        select(Template)
        .where(Template.uploaded_by == user_id)
        .order_by(Template.created_at.desc())
    )
    return list(result.scalars().all())
