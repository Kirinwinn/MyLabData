"""Public schemas for scanned incoming packages."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PackageKind = Literal["molecules", "annotations"]


class PackageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_id: str
    package_kind: PackageKind
    package_name: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime


class PackageDetail(PackageSummary):
    files: list[str]


class PackageActionAccepted(BaseModel):
    package_id: str
    job_id: str
    status: Literal["queued"] = "queued"


class PackageImportRequest(BaseModel):
    """Confirmation token required for Annotation Package import."""

    preview_token: str | None = Field(default=None, min_length=1)
