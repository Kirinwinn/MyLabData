"""Serialized request and result models for building Annotation Packages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.manifest import ENTRY_KEY_PATTERN, KEY_PATTERN

PACKAGE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$"


class SourceFileSummary(BaseModel):
    """One uploaded source data file ready for column mapping."""

    model_config = ConfigDict(frozen=True)

    name: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime


class ColumnProfile(BaseModel):
    """One source column with its inferred value type and fill counts."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    name: str
    value_type: Literal["number", "text", "boolean"]
    filled_rows: int = Field(ge=0)
    empty_rows: int = Field(ge=0)


class SourceFileProfile(BaseModel):
    """The parsed shape of one source data file."""

    model_config = ConfigDict(frozen=True)

    name: str
    encoding: str
    delimiter: str
    columns: list[ColumnProfile]
    total_rows: int = Field(ge=0)
    preview_rows: list[list[str]]


class AttributeChoice(BaseModel):
    """Reuse one registered Attribute or create a new one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["existing", "new"]
    attribute_key: str = Field(pattern=KEY_PATTERN)
    attribute_name: str | None = Field(default=None, min_length=1)
    value_type: Literal["number", "text", "boolean"] | None = None
    unit: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_new_fields(self) -> AttributeChoice:
        if self.mode == "new":
            if self.attribute_name is None:
                raise ValueError("attribute_name is required when creating a new Attribute")
            if self.value_type is None:
                raise ValueError("value_type is required when creating a new Attribute")
        return self


class EntryChoice(BaseModel):
    """Reuse one registered Entry or create a new one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["existing", "new"]
    entry_key: str = Field(pattern=ENTRY_KEY_PATTERN)
    annotation_kind: Literal["prediction", "calculation", "property"] | None = None
    method_name: str | None = Field(default=None, min_length=1)
    method_version: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    is_mutable: bool = False
    description: str | None = None

    @model_validator(mode="after")
    def validate_new_fields(self) -> EntryChoice:
        if self.mode == "new":
            if self.annotation_kind is None:
                raise ValueError("annotation_kind is required when creating a new Entry")
            if self.method_name is None:
                raise ValueError("method_name is required when creating a new Entry")
        if self.annotation_kind != "property" and self.is_mutable:
            raise ValueError("only property entries may be mutable")
        return self


class ColumnMapping(BaseModel):
    """Map one source value column onto one Attribute and one Entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    column_index: int = Field(ge=0)
    column_name: str = Field(min_length=1)
    attribute: AttributeChoice
    entry: EntryChoice


class PackageBuildRequest(BaseModel):
    """Compose one Annotation Package from an uploaded source data file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_name: str = Field(pattern=PACKAGE_NAME_PATTERN)
    source_file: str = Field(min_length=1, max_length=200)
    identifier_column_index: int = Field(ge=0)
    processor_name: str = Field(min_length=1)
    processor_version: str = Field(min_length=1)
    mappings: list[ColumnMapping] = Field(min_length=1)
    dry_run: bool = False

    @model_validator(mode="after")
    def validate_mappings(self) -> PackageBuildRequest:
        indexes = [mapping.column_index for mapping in self.mappings]
        if len(set(indexes)) != len(indexes):
            raise ValueError("Each source column can only be mapped once")
        if self.identifier_column_index in indexes:
            raise ValueError("The identifier column cannot also be a value column")
        return self


class PackageBuildResult(BaseModel):
    """Preflight statistics and the outcome of one package build."""

    model_config = ConfigDict(frozen=True)

    dry_run: bool
    package_name: str
    attributes_existing: int = Field(ge=0)
    attributes_new: int = Field(ge=0)
    entries_existing: int = Field(ge=0)
    entries_new: int = Field(ge=0)
    annotation_rows: int = Field(ge=0)
    linkable_molecules: int = Field(ge=0)
    unlinkable_molecules: int = Field(ge=0)
    in_file_duplicates: int = Field(ge=0)
    already_in_database: int = Field(ge=0)
    expected_inserts: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    warnings: list[str]
