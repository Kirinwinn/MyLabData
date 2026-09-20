"""HTTP endpoints for uploaded source data files beneath DryData/New."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status

from access.paths import DryDataPathError
from api.dependencies import get_job_manager
from jobs.manager import JobManager
from schemas.builder import SourceFileProfile, SourceFileSummary
from services.commands import DryDataCommands
from services.queries import DryDataQueries

router = APIRouter(prefix="/source-files", tags=["source-files"])
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]


@router.get("", response_model=list[SourceFileSummary])
def list_source_files(manager: ManagerDependency) -> list[SourceFileSummary]:
    """List the source data files available for building packages."""
    return DryDataQueries(manager.settings).list_source_files()


@router.post("", response_model=SourceFileProfile, status_code=status.HTTP_201_CREATED)
async def upload_source_file(
    file: UploadFile,
    manager: ManagerDependency,
    overwrite: bool = False,
) -> SourceFileProfile:
    """Store one uploaded source data file and return its parsed shape."""
    content = await file.read()
    name = file.filename or ""
    try:
        DryDataCommands(manager.settings).store_source_file(name, content, overwrite=overwrite)
        return DryDataQueries(manager.settings).profile_source_file(name)
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DryDataPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/{name}/profile", response_model=SourceFileProfile)
def profile_source_file(name: str, manager: ManagerDependency) -> SourceFileProfile:
    """Re-read the parsed shape of one stored source data file."""
    try:
        return DryDataQueries(manager.settings).profile_source_file(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found"
        ) from exc
    except (DryDataPathError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_file(name: str, manager: ManagerDependency) -> Response:
    """Delete one stored source data file."""
    try:
        DryDataCommands(manager.settings).delete_source_file(name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found"
        ) from exc
    except DryDataPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
