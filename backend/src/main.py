"""FastAPI application entry point and background worker lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from api.v1.router import router as api_v1_router
from core.config import Settings, get_settings
from core.exceptions import (
    ConflictError,
    DatabaseError,
    MyLabDataError,
    ValidationError,
)
from core.version import __version__
from jobs.handlers import register_builtin_handlers
from jobs.manager import JobManager


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

    @application.get("/", include_in_schema=False)
    @application.get("/{client_path:path}", include_in_schema=False)
    async def frontend_application(client_path: str = "") -> FileResponse:
        """Serve an optional built SPA without intercepting missing API endpoints."""
        if client_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        frontend_dist = (settings or get_settings()).frontend_dist_directory
        if frontend_dist is None or not (frontend_dist / "index.html").is_file():
            raise HTTPException(status_code=404, detail="Frontend build is not configured")
        requested = (frontend_dist / client_path).resolve()
        if frontend_dist.resolve() in requested.parents and requested.is_file():
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")

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
