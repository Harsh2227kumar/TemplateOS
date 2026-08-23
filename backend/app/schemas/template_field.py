from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class TemplateFieldBase(BaseModel):
    field_name: str = Field(..., max_length=100)
    field_type: str = Field(default="text", max_length=20)
    default_value: str | None = Field(default=None, max_length=255)
    is_required: bool = Field(default=True)
    description: str | None = Field(default=None)
    display_order: int = Field(default=0)

class TemplateFieldCreate(TemplateFieldBase):
    pass

class TemplateFieldUpdate(BaseModel):
    field_name: str | None = Field(None, max_length=100)
    field_type: str | None = Field(None, max_length=20)
    default_value: str | None = Field(None, max_length=255)
    is_required: bool | None = None
    description: str | None = None
    display_order: int | None = None

class TemplateFieldRead(TemplateFieldBase):
    id: int
    template_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
