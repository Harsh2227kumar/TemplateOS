from fastapi import APIRouter

from app.api.v1.endpoints import auth, storage, system, templates

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
