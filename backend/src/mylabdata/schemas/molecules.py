"""Validated results for Molecules scanning, preview, and import."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MoleculeFileCandidate(BaseModel):
    """One Parquet file discovered in Incoming/Molecules."""

    model_config = ConfigDict(frozen=True)

    path: Path
    file_name: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime


class MoleculeImportPreview(BaseModel):
    """Read-only Molecules import counts for one exact file revision."""

    model_config = ConfigDict(frozen=True)

    file_path: Path
    file_name: str
    file_hash: str
    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    new_rows: int = Field(ge=0)
    existing_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)


class MoleculeImportResult(MoleculeImportPreview):
    """Committed Molecules import result and audit identifier."""

    import_id: int = Field(gt=0)
    inserted_rows: int = Field(ge=0)
    status: Literal["completed"] = "completed"

