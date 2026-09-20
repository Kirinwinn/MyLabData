"""Shared FastAPI dependencies."""

from fastapi import Request

from core.config import Settings
from jobs.manager import JobManager


def get_job_manager(request: Request) -> JobManager:
    """Return the application-scoped background job manager."""
    return request.app.state.job_manager


def get_app_settings(request: Request) -> Settings:
    """Return the settings bound to this application instance."""
    return get_job_manager(request).settings
