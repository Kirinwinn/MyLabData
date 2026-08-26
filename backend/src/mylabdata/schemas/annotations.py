"""Validated Annotation Package preview results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mylabdata.contracts.manifest import AttributeDefinition, EntryDefinition


class AttributePreviewItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition: AttributeDefinition
    status: Literal["existing", "new", "conflict"]
    conflicts: list[str] = Field(default_factory=list)


class EntryPreviewItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    definition: EntryDefinition
    status: Literal["existing", "new", "conflict"]
    conflicts: list[str] = Field(default_factory=list)


class AnnotationPackagePreview(BaseModel):
    """Complete, non-mutating preview for one package revision."""

    model_config = ConfigDict(frozen=True)

    package_name: str
    package_hash: str
    preview_token: str
    annotation_rows: int = Field(ge=0)
    attributes: list[AttributePreviewItem]
    entries: list[EntryPreviewItem]
    linkable_molecules: int = Field(ge=0)
    unlinkable_molecules: int = Field(ge=0)
    duplicate_annotations: int = Field(ge=0)
    existing_annotations: int = Field(ge=0)
    expected_inserts: int = Field(ge=0)
    warnings: list[str]
    errors: list[str]
    can_import: bool


class AnnotationImportResult(BaseModel):
    """Committed Annotation import result and package disposition."""

    model_config = ConfigDict(frozen=True)

    import_id: int = Field(gt=0)
    package_name: str
    package_hash: str
    annotation_rows: int = Field(ge=0)
    inserted_annotations: int = Field(ge=0)
    existing_annotations: int = Field(ge=0)
    duplicate_annotations: int = Field(ge=0)
    unlinkable_molecules: int = Field(ge=0)
    created_sources: int = Field(ge=0)
    created_attributes: int = Field(ge=0)
    created_entries: int = Field(ge=0)
    package_moved: bool
    destination: str | None = None
    warnings: list[str] = Field(default_factory=list)
