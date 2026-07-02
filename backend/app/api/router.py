from fastapi import APIRouter
from app.api.migration import router as migration_router
from app.api.status import router as status_router
from app.api.download import router as download_router

router = APIRouter()

router.include_router(migration_router)
router.include_router(status_router)
router.include_router(download_router)
