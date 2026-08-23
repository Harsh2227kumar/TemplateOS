"""
Template Field model for storing extracted DOCX placeholders.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.template import Template

FIELD_TYPES = ("text", "date", "number", "dropdown", "signature")

class TemplateField(Base):
    __tablename__ = "template_fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), default="text", server_default="text")
    default_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    template: Mapped["Template"] = relationship("Template", back_populates="fields")

    @validates("field_type")
    def validate_field_type(self, _key: str, field_type: str) -> str:
        if field_type not in FIELD_TYPES:
            raise ValueError(f"Unsupported field type: {field_type}")
        return field_type
