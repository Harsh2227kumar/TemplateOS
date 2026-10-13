from app.models.user import User
from app.models.template import Template
from app.models.template_field import TemplateField
from app.models.ai_generation import AiGeneration
from app.models.document import Document
from app.models.document_value import DocumentValue
from app.models.refresh_token import RefreshToken
from app.models.generated_file import GeneratedFile

# Remove generated DOCX/PDF files from storage when their rows are deleted.
from app.services.generated_file_cleanup import register as _register_cleanup

_register_cleanup()
