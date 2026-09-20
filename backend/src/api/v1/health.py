"""Basic process health endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is running.

    Database health checks will be added with the DuckDB layer.
    """
    return {"status": "ok"}
