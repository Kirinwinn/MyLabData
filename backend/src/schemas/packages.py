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


class MoleculePackagePreview(BaseModel):
    """Path-free result returned by a Molecules preview Job."""

    model_config = ConfigDict(frozen=True)

    package_name: str
    package_hash: str
    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    new_rows: int = Field(ge=0)
    existing_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)


class PackageImportResult(BaseModel):
    """Common committed result returned by a Package import Job."""

    model_config = ConfigDict(frozen=True)

    import_id: int = Field(gt=0)
    package_name: str
    package_hash: str
    total_rows: int = Field(ge=0)
    inserted_rows: int = Field(ge=0)
    existing_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)
    created_attributes: int = Field(ge=0)
    created_entries: int = Field(ge=0)
    created_sources: int = Field(ge=0)
    archived: bool
