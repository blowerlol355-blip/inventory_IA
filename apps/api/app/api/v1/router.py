from fastapi import APIRouter

from app.api.v1 import auth, conversations, documents, files

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(conversations.router)
api_router.include_router(files.router)
