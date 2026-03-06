from fastapi import APIRouter

from .avito.router import router as avito_router
from .max.router import router as max_router
from .vahta_ai.router import router as vahta_ai_router

main_router = APIRouter()

main_router.include_router(avito_router)
main_router.include_router(max_router)
main_router.include_router(vahta_ai_router)
