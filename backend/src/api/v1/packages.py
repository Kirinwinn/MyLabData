"""HTTP endpoints that submit package Query and Command Jobs by opaque ID."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_job_manager
from jobs.manager import JobManager
from jobs.schemas import JobAccepted
from schemas.builder import PackageBuildRequest
from schemas.packages import PackageActionAccepted, PackageImportRequest

router = APIRouter(prefix="/packages", tags=["packages"])
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]


@router.post(
    "/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def list_packages(manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "packages_query", {})


@router.post(
    "/build",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_package(request: PackageBuildRequest, manager: ManagerDependency) -> JobAccepted:
    """Submit a Command Job that composes an Annotation Package from a source file."""
    return _submit(manager, "package_build", request.model_dump(mode="json"))


@router.post(
    "/{package_id}/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def read_package(package_id: str, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "package_query", {"package_id": package_id})


@router.post(
    "/{package_id}/preview",
    response_model=PackageActionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def preview_package(package_id: str, manager: ManagerDependency) -> PackageActionAccepted:
    job = _submit(manager, "package_preview", {"package_id": package_id})
    return PackageActionAccepted(package_id=package_id, job_id=job.job_id)


@router.post(
    "/{package_id}/imports",
    response_model=PackageActionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_package(
    package_id: str,
    manager: ManagerDependency,
    request: PackageImportRequest | None = None,
) -> PackageActionAccepted:
    payload = {"package_id": package_id}
    if request is not None and request.preview_token is not None:
        payload["preview_token"] = request.preview_token
    job = _submit(manager, "package_import", payload)
    return PackageActionAccepted(package_id=package_id, job_id=job.job_id)


def _submit(manager: JobManager, job_type: str, payload: dict[str, Any]) -> JobAccepted:
    try:
        job = manager.submit(job_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JobAccepted(job_id=job.job_id)
