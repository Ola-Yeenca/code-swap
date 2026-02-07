from fastapi import APIRouter

from app.api.routes import auth, billing, chat, compare, crew, files, gdpr, keys, models, usage, workspaces

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(keys.router, tags=["keys"])
api_router.include_router(models.router, tags=["models"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(compare.router, tags=["compare"])
api_router.include_router(files.router, tags=["files"])
api_router.include_router(workspaces.router, tags=["workspaces"])
api_router.include_router(usage.router, tags=["usage"])
api_router.include_router(billing.router, tags=["billing"])
api_router.include_router(gdpr.router, tags=["gdpr"])
api_router.include_router(crew.router, tags=["crew"])
