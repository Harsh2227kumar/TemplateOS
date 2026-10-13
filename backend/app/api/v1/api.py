from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    auth,
    documents,
    system,
    template_ai,
    template_cleaning,
    template_fields,
    template_placeholders,
    templates,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
# The /templates routers are included in this order on purpose: `templates`
# declares the static /library and /access-options routes before
# /{template_id}, and the sequence reproduces the original route order.
for template_router in (
    templates.router,
    template_placeholders.router,
    template_cleaning.router,
    template_ai.router,
    template_fields.router,
):
    api_router.include_router(template_router, prefix="/templates", tags=["templates"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
