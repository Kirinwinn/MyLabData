"""HTTP and SSE endpoints for background job coordination."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from access.paths import DryDataPathError, DryDataPaths
from api.dependencies import get_job_manager
from jobs.manager import JobManager
from jobs.schemas import SEARCH_EXPORT_JOB_TYPE, SMILES_EXPORT_JOB_TYPE, JobRecord

router = APIRouter(prefix="/jobs", tags=["jobs"])
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]
STREAM_END_STATES = {
    "waiting_confirmation",
    "archive_pending",
    "completed",
    "failed",
    "cancelled",
}
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"
EXPORT_JOB_TYPES = {SEARCH_EXPORT_JOB_TYPE, SMILES_EXPORT_JOB_TYPE}


@router.get("", response_model=list[JobRecord])
def get_background_jobs(
    manager: ManagerDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JobRecord]:
    """List recent persistent job records."""
    return manager.list(limit=limit)


@router.get("/{job_id}", response_model=JobRecord)
def get_background_job(job_id: str, manager: ManagerDependency) -> JobRecord:
    """Return the latest persistent state of one job."""
    return _get_or_404(manager, job_id)


@router.post("/{job_id}/cancel", response_model=JobRecord)
def cancel_background_job(job_id: str, manager: ManagerDependency) -> JobRecord:
    """Cancel queued work or request cooperative cancellation of running work."""
    try:
        return manager.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/{job_id}/events")
def stream_background_job(job_id: str, manager: ManagerDependency) -> StreamingResponse:
    """Stream state snapshots until the job stops or needs confirmation."""
    _get_or_404(manager, job_id)

    async def events() -> AsyncIterator[str]:
        last_updated = None
        while True:
            try:
                job = await asyncio.to_thread(manager.get, job_id)
            except KeyError:
                yield _sse("error", {"detail": "Job not found"})
                return
            marker = job.updated_at.isoformat()
            if marker != last_updated:
                yield _sse("job", job.model_dump(mode="json"))
                last_updated = marker
            if job.status in STREAM_END_STATES:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/export")
def download_export_workbook(job_id: str, manager: ManagerDependency) -> FileResponse:
    """Download the workbook or archive produced by a completed export Job."""
    job = _get_or_404(manager, job_id)
    ready = job.job_type in EXPORT_JOB_TYPES and job.status == "completed"
    if not ready or job.result is None:
        raise HTTPException(status_code=404, detail="Export file is not available for this job")
    file_name = job.result.get("file_name")
    if not isinstance(file_name, str) or not file_name:
        raise HTTPException(status_code=404, detail="Export file is not available for this job")
    paths = DryDataPaths(manager.settings.data_root)
    try:
        target = paths.require_within_root(paths.exports_directory / file_name, must_exist=True)
    except (DryDataPathError, OSError) as exc:
        raise HTTPException(status_code=404, detail="Export file is missing") from exc
    media_type = XLSX_MEDIA_TYPE if file_name.endswith(".xlsx") else ZIP_MEDIA_TYPE
    return FileResponse(target, media_type=media_type, filename=file_name)


def _get_or_404(manager: JobManager, job_id: str) -> JobRecord:
    try:
        return manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
