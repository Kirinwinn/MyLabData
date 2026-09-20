"""Pydantic contracts for Annotation Package JSON documents."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY_PATTERN = r"^[a-z][a-z0-9_]*$"
ENTRY_KEY_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[A-Za-z0-9_#()\[\]=+\-]+)*$"


class AttributeDefinition(BaseModel):
    """One metric definition declared by an Annotation Package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attribute_key: str = Field(pattern=KEY_PATTERN)
    attribute_name: str = Field(min_length=1)
    value_type: Literal["number", "text", "boolean"]
    unit: str | None = None
    description: str | None = None


class EntryDefinition(BaseModel):
    """One method-and-condition result definition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_key: str = Field(pattern=ENTRY_KEY_PATTERN)
    attribute_key: str = Field(pattern=KEY_PATTERN)
    annotation_kind: Literal["prediction", "calculation", "property"]
    method_name: str = Field(min_length=1)
    method_version: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    source_key: str | None = None
    is_mutable: bool = False
    description: str | None = None

    @model_validator(mode="after")
    def validate_mutability(self) -> "EntryDefinition":
        if self.annotation_kind != "property" and self.is_mutable:
            raise ValueError("only property entries may be mutable")
        return self


class AnnotationManifest(BaseModel):
    """Version 1.0 Annotation Package manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    processor_name: str = Field(min_length=1)
    processor_version: str = Field(min_length=1)
    attributes: list[AttributeDefinition] = Field(min_length=1)
    entries: list[EntryDefinition] = Field(min_length=1)
    data_files: list[str] = Field(min_length=1)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_definition_graph(self) -> "AnnotationManifest":
        attribute_keys = [item.attribute_key for item in self.attributes]
        entry_keys = [item.entry_key for item in self.entries]
        if len(attribute_keys) != len(set(attribute_keys)):
            raise ValueError("attribute_key values must be unique")
        if len(entry_keys) != len(set(entry_keys)):
            raise ValueError("entry_key values must be unique")
        unknown = {item.attribute_key for item in self.entries} - set(attribute_keys)
        if unknown:
            raise ValueError(f"entries reference unknown attributes: {sorted(unknown)}")
        if self.data_files != ["annotations.parquet"]:
            raise ValueError("schema 1.0 currently requires data_files=['annotations.parquet']")
        return self


class ProcessingReport(BaseModel):
    """Processing summary produced alongside the Annotation data."""

    model_config = ConfigDict(extra="allow", frozen=True)

    status: Literal["completed", "failed"]
    input_rows: int = Field(ge=0)
    output_annotations: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    warnings: list[str]
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_times(self) -> "ProcessingReport":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self
