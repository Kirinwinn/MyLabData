"""Top-level API v1 router."""

from fastapi import APIRouter

from api.v1.catalog import router as catalog_router
from api.v1.health import router as health_router
from api.v1.jobs import router as jobs_router
from api.v1.packages import router as packages_router
from api.v1.source_files import router as source_files_router

router = APIRouter()
router.include_router(health_router)
router.include_router(jobs_router)
router.include_router(packages_router)
router.include_router(source_files_router)
router.include_router(catalog_router)
