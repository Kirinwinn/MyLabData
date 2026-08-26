"""API and service schemas for background jobs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal[
    "queued",
    "validating",
    "waiting_confirmation",
    "importing",
    "completed",
    "failed",
    "cancelled",
]


class JobCreate(BaseModel):
    """Request to enqueue one registered background operation."""

    job_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    """Persistent public representation of a background job."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    job_type: str
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
    """Minimal response returned immediately after enqueueing."""

    job_id: str
    status: Literal["queued"] = "queued"
