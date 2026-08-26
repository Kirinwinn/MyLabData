"""Safe Package-ID based preview and import endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from mylabdata.api.dependencies import get_app_settings, get_job_manager
from mylabdata.core.config import Settings
from mylabdata.jobs.manager import JobManager
from mylabdata.schemas.packages import (
    PackageActionAccepted,
    PackageDetail,
    PackageImportRequest,
    PackageSummary,
)
from mylabdata.services.package_scanner import get_package, scan_packages

router = APIRouter(prefix="/packages", tags=["packages"])
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]


@router.get("", response_model=list[PackageSummary])
def list_packages(settings: SettingsDependency) -> list[PackageSummary]:
    """Scan trusted incoming roots and return opaque package identifiers."""
    return scan_packages(settings)


@router.get("/{package_id}", response_model=PackageDetail)
def read_package(package_id: str, settings: SettingsDependency) -> PackageDetail:
    """Resolve one ID by rescanning; never accept a client filesystem path."""
    return _package_or_404(package_id, settings)[0]


@router.post(
    "/{package_id}/preview",
    response_model=PackageActionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def preview_package(
    package_id: str,
    settings: SettingsDependency,
    manager: ManagerDependency,
) -> PackageActionAccepted:
    detail, _ = _package_or_404(package_id, settings)
    job_type = "molecule_preview" if detail.package_kind == "molecules" else "annotation_preview"
    job = _submit(manager, job_type, package_id)
    return PackageActionAccepted(package_id=package_id, job_id=job.job_id)


@router.post(
    "/{package_id}/imports",
    response_model=PackageActionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_package(
    package_id: str,
    settings: SettingsDependency,
    manager: ManagerDependency,
    request: PackageImportRequest | None = None,
) -> PackageActionAccepted:
    detail, _ = _package_or_404(package_id, settings)
    if detail.package_kind == "annotations":
        if request is None or request.preview_token is None:
            raise HTTPException(
                status_code=422,
                detail="preview_token is required for Annotation import",
            )
        job = _submit(
            manager,
            "annotation_import",
            package_id,
            preview_token=request.preview_token,
        )
    else:
        job = _submit(manager, "molecule_import", package_id)
    return PackageActionAccepted(package_id=package_id, job_id=job.job_id)


def _package_or_404(package_id: str, settings: Settings) -> tuple[PackageDetail, Path]:
    try:
        return get_package(package_id, settings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Package not found") from exc


def _submit(
    manager: JobManager,
    job_type: str,
    package_id: str,
    **payload: str,
):
    try:
        return manager.submit(job_type, {"package_id": package_id, **payload})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
