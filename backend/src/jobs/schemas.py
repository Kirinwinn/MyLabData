"""Public records and validated values for persistent Jobs."""

from datetime import datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

SEARCH_EXPORT_JOB_TYPE: Final[str] = "search_export"
SMILES_EXPORT_JOB_TYPE: Final[str] = "smiles_export"

JobKind = Literal["query", "command"]
JobStatus = Literal[
    "queued",
    "validating",
    "waiting_confirmation",
    "running",
    "importing",
    "archiving",
    "archive_pending",
    "completed",
    "failed",
    "cancelled",
]


class JobCreate(BaseModel):
    """Internal request to enqueue one registered operation."""

    job_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    """Persistent public representation of one Job work order."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    job_type: str
    job_kind: JobKind
    status: JobStatus
    progress: float = Field(ge=0, le=1)
    message: str | None
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class JobAccepted(BaseModel):
    """Minimal response returned immediately after accepting a Job."""

    job_id: str
    status: Literal["queued"] = "queued"
