"""Serialized read models exposed by the FastAPI catalog endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImportRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    import_id: int
    source_id: int | None
    file_hash: str | None
    data_type: str | None
    status: str | None
    processor: str | None
    total_rows: int | None
    error_message: str | None
    created_at: datetime | None
    finished_at: datetime | None


class MoleculeSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    molecule_id: int
    lab_id: str
    canonical_smiles: str
    channel: str | None = None
    created_at: datetime | None


class MoleculeDetail(MoleculeSummary):
    pass


class Molecule3DStructure(BaseModel):
    """A temporary 3D structure generated from a molecule's canonical SMILES."""

    model_config = ConfigDict(frozen=True)

    molecule_id: int
    canonical_smiles: str
    mol_block: str


class AttributeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    attribute_id: int
    attribute_key: str
    attribute_name: str
    value_type: str
    unit: str | None
    description: str | None


class MoleculeAttributeAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: int
    entry_key: str
    annotation_kind: str
    method_name: str
    method_version: str | None
    conditions: dict[str, Any]
    is_mutable: bool
    description: str | None
    value: float | str | bool
    updated_at: datetime | None


class EntryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: int
    attribute_id: int
    entry_key: str
    annotation_kind: str
    method_name: str
    method_version: str | None
    conditions: dict[str, Any]
    is_mutable: bool
    description: str | None


class DatabaseStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    molecules: int = Field(ge=0)
    attributes: int = Field(ge=0)
    entries: int = Field(ge=0)
    annotations: int = Field(ge=0)
    imports: int = Field(ge=0)
    jobs: int = Field(ge=0)


class SearchCondition(BaseModel):
    attribute_id: int | None = Field(default=None, gt=0)
    attribute_key: str | None = None
    entry_id: int | None = Field(default=None, gt=0)
    entry_key: str | None = None
    operator: Literal[
        "eq",
        "ne",
        "lt",
        "lte",
        "gt",
        "gte",
        "between",
        "contains",
        "starts_with",
        "ends_with",
    ]
    value: Any
    second_value: Any | None = None

    @model_validator(mode="after")
    def require_catalog_identifiers(self) -> "SearchCondition":
        attributes = (self.attribute_id, self.attribute_key)
        entries = (self.entry_id, self.entry_key)
        if sum(value is not None for value in attributes) != 1:
            raise ValueError("provide exactly one Attribute identifier")
        if sum(value is not None for value in entries) != 1:
            raise ValueError("provide exactly one Entry identifier")
        return self


class SearchRequest(BaseModel):
    conditions: list[SearchCondition] = Field(min_length=1, max_length=50)
    logic: Literal["and", "or"] = "and"
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class PageQueryRequest(BaseModel):
    """Pagination input for a Query Job that returns a collection."""

    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class EntryFilter(BaseModel):
    """Select molecules by the presence or absence of one entry's results."""

    model_config = ConfigDict(frozen=True)

    entry_id: int = Field(ge=1)
    has_results: bool


class MoleculeListQueryRequest(PageQueryRequest):
    """Optional text filter and pagination for a molecule Query Job."""

    query: str | None = Field(default=None, max_length=500)
    entry_filter: EntryFilter | None = None


class MoleculeListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[MoleculeSummary]
    total: int = Field(ge=0)


class EntryIndexRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: int
    entry_key: str
    attribute_key: str
    attribute_name: str
    annotation_kind: str
    method_name: str
    method_version: str | None
    conditions: dict[str, Any]
    is_mutable: bool
    description: str | None


class PropertyUpdateRequest(BaseModel):
    value_number: float | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    source: str = Field(min_length=1)

    @field_validator("value_number", mode="before")
    @classmethod
    def reject_boolean_number(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("value_number cannot be boolean")
        return value

    @field_validator("value_boolean", mode="before")
    @classmethod
    def require_boolean(cls, value: Any) -> Any:
        if value is not None and type(value) is not bool:
            raise ValueError("value_boolean must be boolean")
        return value

    @model_validator(mode="after")
    def exactly_one_value(self) -> "PropertyUpdateRequest":
        values = (self.value_number, self.value_text, self.value_boolean)
        if sum(value is not None for value in values) != 1:
            raise ValueError("exactly one property value must be provided")
        return self


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    molecules: list[MoleculeSummary]
    elapsed_ms: float = Field(ge=0)
    limit: int
    offset: int
    total: int = Field(ge=0)


class SearchExportSheet(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=31)
    row_count: int = Field(ge=0)


class SearchExportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    logic: Literal["and", "or"]
    total: int = Field(ge=0)
    sheets: list[SearchExportSheet] = Field(min_length=2)


class SmilesExportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows_per_file: int = Field(default=50_000, ge=1, le=2_000_000)
    entry_filter: EntryFilter | None = None


class SmilesExportResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_name: str = Field(min_length=1)
    total: int = Field(ge=0)
    rows_per_file: int = Field(ge=1)
    files: list[str] = Field(min_length=1)


class PropertyUpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    molecule_id: int
    entry_id: int
    value_number: float | None
    value_text: str | None
    value_boolean: bool | None
    source: str
    created: bool
    updated_at: datetime


class AttributeStatistics(BaseModel):
    model_config = ConfigDict(frozen=True)

    attribute_id: int
    entry_id: int
    entry_key: str
    value_type: str
    count: int = Field(ge=0)
    distinct_count: int = Field(ge=0)
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    true_count: int | None = Field(default=None, ge=0)
    false_count: int | None = Field(default=None, ge=0)


class StatisticsPreheatResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    preheated: int = Field(ge=0)
    failed: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
