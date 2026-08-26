"""FastAPI application entry point and background worker lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mylabdata import __version__
from mylabdata.api.v1.router import router as api_v1_router
from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import (
    ConflictError,
    DatabaseError,
    MyLabDataError,
    ValidationError,
)
from mylabdata.jobs.handlers import register_builtin_handlers
from mylabdata.jobs.manager import JobManager


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the MyLabData FastAPI application."""
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or get_settings()
        manager = JobManager(resolved_settings)
        register_builtin_handlers(manager)
        manager.start()
        application.state.job_manager = manager
        try:
            yield
        finally:
            manager.stop(wait=True)

    application = FastAPI(
        title="MyLabData",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(api_v1_router, prefix="/api/v1")

    @application.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(ConflictError)
    async def conflict_error_handler(
        request: Request,
        exc: ConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(DatabaseError)
    async def database_error_handler(
        request: Request,
        exc: DatabaseError,
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(MyLabDataError)
    async def application_error_handler(
        request: Request,
        exc: MyLabDataError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    return application


app = create_app()
