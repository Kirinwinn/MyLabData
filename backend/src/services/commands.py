"""Business-level Command operations backed exclusively by ``access`` objects."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from access.annotations import AnnotationRepository
from access.cache import CacheStore
from access.catalog import STATISTICS_NAMESPACE, CatalogRepository
from access.database import DryDataDatabase
from access.imports import ImportRepository, PackageImportSummary
from access.molecules import MoleculeRepository
from access.packages import PackageStore
from access.paths import DryDataPaths
from access.source_files import SourceFileStore
from contracts.manifest import AnnotationManifest, ProcessingReport
from core.config import Settings
from schemas.builder import (
    AttributeChoice,
    EntryChoice,
    PackageBuildRequest,
    PackageBuildResult,
    SourceFileSummary,
)
from schemas.catalog import PropertyUpdateRequest, PropertyUpdateResult


@dataclass(frozen=True, slots=True)
class DryDataCommands:
    """Coordinate domain writes without owning SQL, paths, or file operations."""

    settings: Settings
    paths: DryDataPaths = field(init=False)
    database: DryDataDatabase = field(init=False)
    annotations: AnnotationRepository = field(init=False)
    catalog: CatalogRepository = field(init=False)
    imports: ImportRepository = field(init=False)
    molecules: MoleculeRepository = field(init=False)
    packages: PackageStore = field(init=False)
    cache: CacheStore = field(init=False)
    source_files: SourceFileStore = field(init=False)

    def __post_init__(self) -> None:
        paths = DryDataPaths(self.settings.data_root)
        paths.ensure_runtime_directories()
        database = DryDataDatabase(
            paths,
            config={
                "memory_limit": self.settings.memory_limit,
                "threads": str(self.settings.threads),
                "temp_directory": str(paths.temp_directory),
            },
        )
        object.__setattr__(self, "paths", paths)
        object.__setattr__(self, "database", database)
        object.__setattr__(self, "annotations", AnnotationRepository(database))
        object.__setattr__(self, "catalog", CatalogRepository(database, CacheStore(paths)))
        object.__setattr__(self, "imports", ImportRepository(database))
        object.__setattr__(self, "molecules", MoleculeRepository(database))
        object.__setattr__(self, "packages", PackageStore(paths))
        object.__setattr__(self, "cache", CacheStore(paths))
        object.__setattr__(self, "source_files", SourceFileStore(paths))

    def import_package(
        self,
        package_id: str,
        *,
        preview_token: str | None = None,
    ) -> tuple[PackageImportSummary, bool]:
        """Commit a managed package, then archive it through the access layer."""
        descriptor = self.packages.descriptor(package_id)
        if descriptor.kind == "annotations":
            current_hash = self.packages.fingerprint(package_id)
            expected_token = f"annotation-preview-v1:{descriptor.name}:{current_hash}"
            if preview_token != expected_token:
                raise ValueError("Annotation preview token is invalid or the package changed")
            manifest = AnnotationManifest.model_validate(
                self.packages.read_json(package_id, "annotation_manifest.json")
            )
            with self.database.transaction() as connection:
                result = self.imports.import_annotation_package(
                    connection,
                    self.packages,
                    package_id,
                    manifest,
                )
        else:
            with self.database.transaction() as connection:
                result = self.imports.import_molecule_package(
                    connection,
                    self.packages,
                    package_id,
                )
        self.cache.invalidate_namespace(STATISTICS_NAMESPACE)
        try:
            self.packages.archive(package_id, "processed")
        except OSError:
            return result, False
        return result, True

    def update_property(
        self,
        molecule_id: int,
        entry_id: int,
        request: PropertyUpdateRequest,
    ) -> PropertyUpdateResult:
        """Update one mutable Property through the v3 access boundary."""
        source = request.source.strip()
        if not source:
            raise ValueError("Property update source must not be blank")
        with self.database.transaction() as connection:
            outcome = self.annotations.upsert_mutable_property(
                connection,
                molecule_id=molecule_id,
                entry_id=entry_id,
                value_number=request.value_number,
                value_text=request.value_text,
                value_boolean=request.value_boolean,
            )
        self.cache.invalidate_namespace(STATISTICS_NAMESPACE)
        return PropertyUpdateResult(
            molecule_id=molecule_id,
            entry_id=entry_id,
            value_number=request.value_number,
            value_text=request.value_text,
            value_boolean=request.value_boolean,
            source=source,
            created=outcome.created,
            updated_at=outcome.updated_at,
        )

    def store_source_file(
        self,
        name: str,
        content: bytes,
        *,
        overwrite: bool = False,
    ) -> SourceFileSummary:
        """Write one uploaded source data file into DryData/New."""
        descriptor = self.source_files.store(name, content, overwrite=overwrite)
        return SourceFileSummary(
            name=descriptor.name,
            size_bytes=descriptor.size_bytes,
            modified_at=descriptor.modified_at,
        )

    def delete_source_file(self, name: str) -> None:
        """Delete one uploaded source data file from DryData/New."""
        self.source_files.delete(name)

    def build_annotation_package(self, request: PackageBuildRequest) -> PackageBuildResult:
        """Compose one Annotation Package from an uploaded source data file.

        Registered definitions are copied verbatim when a key already exists, so a
        package built here never conflicts with the catalog. ``rejected_rows``
        counts skipped identifier rows and skipped value cells.
        """
        started_at = datetime.now(UTC)
        warnings = _WarningLog()
        self._require_free_package_name(request.package_name, warnings)

        header, data_rows = self.source_files.read_rows(request.source_file)
        width = len(header)
        if request.identifier_column_index >= width:
            raise ValueError("identifier_column_index is outside the source file columns")
        for mapping in request.mappings:
            if mapping.column_index >= width:
                raise ValueError(
                    f"column_index {mapping.column_index} is outside the source file columns"
                )

        attribute_definitions: dict[str, dict[str, Any]] = {}
        entry_definitions: dict[str, dict[str, Any]] = {}
        entry_ids: dict[str, int] = {}
        attributes_existing = 0
        attributes_new = 0
        entries_existing = 0
        entries_new = 0
        resolved: list[tuple[int, str, str]] = []
        for mapping in request.mappings:
            attribute_definition, attribute_existed = self._attribute_definition(mapping.attribute)
            attribute_key = str(attribute_definition["attribute_key"])
            entry_definition, entry_existed, entry_id = self._entry_definition(
                mapping.entry, attribute_key
            )
            entry_key = str(entry_definition["entry_key"])
            if attribute_key not in attribute_definitions:
                attribute_definitions[attribute_key] = attribute_definition
                if attribute_existed:
                    attributes_existing += 1
                else:
                    attributes_new += 1
            elif attribute_definitions[attribute_key] != attribute_definition:
                raise ValueError(f"Conflicting definitions for attribute {attribute_key}")
            if entry_key not in entry_definitions:
                entry_definitions[entry_key] = entry_definition
                if entry_existed:
                    entries_existing += 1
                else:
                    entries_new += 1
            elif entry_definitions[entry_key] != entry_definition:
                raise ValueError(f"Conflicting definitions for entry {entry_key}")
            if entry_id is not None:
                entry_ids[entry_key] = entry_id
            resolved.append((mapping.column_index, attribute_key, entry_key))

        smiles_column: list[str] = []
        attribute_column: list[str] = []
        entry_column: list[str] = []
        number_column: list[float | None] = []
        text_column: list[str | None] = []
        boolean_column: list[bool | None] = []
        seen: dict[tuple[str, str], float | str | bool] = {}
        rejected_rows = 0
        duplicate_rows = 0
        for row in data_rows:
            identifier = row[request.identifier_column_index]
            if not identifier:
                rejected_rows += 1
                continue
            for column_index, attribute_key, entry_key in resolved:
                raw = row[column_index]
                if not raw:
                    rejected_rows += 1
                    continue
                value_type = str(attribute_definitions[attribute_key]["value_type"])
                accepted, value = _convert_value(raw, value_type)
                if not accepted:
                    rejected_rows += 1
                    warnings.add(
                        f"Skipped a value that is not {value_type}: {raw[:40]!r} ({entry_key})"
                    )
                    continue
                key = (identifier, entry_key)
                if key in seen:
                    if seen[key] != value:
                        warnings.add(
                            f"Conflicting duplicate value for {identifier[:40]} / {entry_key};"
                            " kept the first"
                        )
                        rejected_rows += 1
                    else:
                        duplicate_rows += 1
                    continue
                seen[key] = value
                smiles_column.append(identifier)
                attribute_column.append(attribute_key)
                entry_column.append(entry_key)
                number_column.append(value if value_type == "number" else None)
                text_column.append(value if value_type == "text" else None)
                boolean_column.append(value if value_type == "boolean" else None)

        distinct_smiles = sorted(set(smiles_column))
        linkable = self.molecules.existing_smiles(distinct_smiles)
        linkable_rows = sum(1 for smiles in smiles_column if smiles in linkable)
        molecule_ids = self.molecules.molecule_ids_for_smiles(sorted(linkable))
        pairs = {
            (molecule_ids[smiles], entry_ids[entry_key])
            for smiles, entry_key in zip(smiles_column, entry_column, strict=True)
            if entry_key in entry_ids and smiles in molecule_ids
        }
        existing_pairs = self.catalog.existing_annotation_pairs(
            molecule_ids=sorted({molecule_id for molecule_id, _ in pairs}),
            entry_ids=sorted({entry_id for _, entry_id in pairs}),
        )
        already_in_database = len(pairs & existing_pairs)

        warning_messages = warnings.finish()
        if rejected_rows:
            warning_messages.append(
                f"{rejected_rows} rows or values were skipped while building the package"
            )
        if duplicate_rows:
            warning_messages.append(
                f"{duplicate_rows} duplicate values were removed while building the package"
            )

        manifest = {
            "schema_version": "1.0",
            "processor_name": request.processor_name,
            "processor_version": request.processor_version,
            "attributes": list(attribute_definitions.values()),
            "entries": list(entry_definitions.values()),
            "data_files": ["annotations.parquet"],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        report = {
            "status": "completed",
            "input_rows": len(data_rows),
            "output_annotations": len(smiles_column),
            "rejected_rows": 0,
            "duplicate_rows": 0,
            "warnings": warning_messages,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        }
        AnnotationManifest.model_validate(manifest)
        ProcessingReport.model_validate(report)

        if not request.dry_run:
            directory = self.paths.package_directory("incoming", "annotations")
            target = self.paths.require_within_root(directory / request.package_name)
            target.mkdir(parents=True)
            _write_annotation_package(
                target,
                _package_table(
                    smiles_column,
                    attribute_column,
                    entry_column,
                    number_column,
                    text_column,
                    boolean_column,
                ),
                manifest,
                report,
            )

        return PackageBuildResult(
            dry_run=request.dry_run,
            package_name=request.package_name,
            attributes_existing=attributes_existing,
            attributes_new=attributes_new,
            entries_existing=entries_existing,
            entries_new=entries_new,
            annotation_rows=len(smiles_column),
            linkable_molecules=len(linkable),
            unlinkable_molecules=len(distinct_smiles) - len(linkable),
            in_file_duplicates=duplicate_rows,
            already_in_database=already_in_database,
            expected_inserts=linkable_rows - already_in_database,
            rejected_rows=rejected_rows,
            warnings=warning_messages,
        )

    def _require_free_package_name(self, package_name: str, warnings: _WarningLog) -> None:
        if (self.paths.package_directory("incoming", "annotations") / package_name).exists():
            raise ValueError(f"A package named {package_name} already exists in Incoming")
        for state in ("processed", "failed"):
            if (self.paths.package_directory(state, "annotations") / package_name).exists():
                warnings.add(
                    f"A package named {package_name} was previously archived under {state.title()}"
                )

    def _attribute_definition(self, choice: AttributeChoice) -> tuple[dict[str, Any], bool]:
        if choice.mode == "existing":
            row = self.catalog.attribute_by_key(choice.attribute_key)
            if row is None:
                raise ValueError(f"Attribute is not registered: {choice.attribute_key}")
            return (
                {
                    "attribute_key": row.attribute_key,
                    "attribute_name": row.attribute_name,
                    "value_type": row.value_type,
                    "unit": row.unit,
                    "description": row.description,
                },
                True,
            )
        return (
            {
                "attribute_key": choice.attribute_key,
                "attribute_name": choice.attribute_name,
                "value_type": choice.value_type,
                "unit": choice.unit,
                "description": choice.description,
            },
            False,
        )

    def _entry_definition(
        self,
        choice: EntryChoice,
        attribute_key: str,
    ) -> tuple[dict[str, Any], bool, int | None]:
        if choice.mode == "existing":
            row = self.catalog.entry_by_key(choice.entry_key)
            if row is None:
                raise ValueError(f"Entry is not registered: {choice.entry_key}")
            if row.attribute_key != attribute_key:
                raise ValueError(
                    f"Entry {row.entry_key} belongs to attribute {row.attribute_key},"
                    f" not {attribute_key}"
                )
            return (
                {
                    "entry_key": row.entry_key,
                    "attribute_key": row.attribute_key,
                    "annotation_kind": row.annotation_kind,
                    "method_name": row.method_name,
                    "method_version": row.method_version,
                    "conditions": row.conditions,
                    "is_mutable": row.is_mutable,
                    "description": row.description,
                },
                True,
                row.entry_id,
            )
        return (
            {
                "entry_key": choice.entry_key,
                "attribute_key": attribute_key,
                "annotation_kind": choice.annotation_kind,
                "method_name": choice.method_name,
                "method_version": choice.method_version,
                "conditions": choice.conditions,
                "is_mutable": choice.is_mutable,
                "description": choice.description,
            },
            False,
            None,
        )


_MAX_WARNING_DETAILS = 10


class _WarningLog:
    """Collect bounded warnings so Job results stay small."""

    def __init__(self, limit: int = _MAX_WARNING_DETAILS) -> None:
        self._limit = limit
        self._messages: list[str] = []
        self._suppressed = 0

    def add(self, message: str) -> None:
        if len(self._messages) < self._limit:
            self._messages.append(message)
        else:
            self._suppressed += 1

    def finish(self) -> list[str]:
        if self._suppressed:
            self._messages.append(f"{self._suppressed} more warnings were suppressed")
        return self._messages


def _convert_value(raw: str, value_type: str) -> tuple[bool, float | str | bool]:
    if value_type == "number":
        try:
            return True, float(raw)
        except ValueError:
            return False, ""
    if value_type == "boolean":
        normalized = raw.casefold()
        if normalized in {"true", "yes", "1"}:
            return True, True
        if normalized in {"false", "no", "0"}:
            return True, False
        return False, ""
    return True, raw


def _package_table(
    smiles: list[str],
    attributes: list[str],
    entries: list[str],
    numbers: list[float | None],
    texts: list[str | None],
    booleans: list[bool | None],
) -> pa.Table:
    return pa.table(
        {
            "canonical_smiles": pa.array(smiles, pa.string()),
            "attribute_key": pa.array(attributes, pa.string()),
            "entry_key": pa.array(entries, pa.string()),
            "value_number": pa.array(numbers, pa.float64()),
            "value_text": pa.array(texts, pa.string()),
            "value_boolean": pa.array(booleans, pa.bool_()),
        }
    )


def _write_annotation_package(
    directory: Path,
    table: pa.Table,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> None:
    pq.write_table(table, directory / "annotations.parquet")
    (directory / "annotation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "processing_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
