"""Non-mutating v3 previews for managed incoming packages."""

from __future__ import annotations

import json

import duckdb
from pydantic import ValidationError as PydanticValidationError

from access.database import DryDataDatabase
from access.packages import PackageStore
from contracts.manifest import AnnotationManifest, ProcessingReport
from schemas.annotations import (
    AnnotationPackagePreview,
    AttributePreviewItem,
    EntryPreviewItem,
)

_REQUIRED = {"annotation_manifest.json", "annotations.parquet", "processing_report.json"}
_ALLOWED = _REQUIRED | {"rejected.parquet"}
_ANNOTATION_COLUMNS = {
    "canonical_smiles": "VARCHAR",
    "attribute_key": "VARCHAR",
    "entry_key": "VARCHAR",
    "value_number": "DOUBLE",
    "value_text": "VARCHAR",
    "value_boolean": "BOOLEAN",
}


class PreviewRepository:
    """Read package files and v3 data without exposing paths to services."""

    def __init__(self, database: DryDataDatabase, packages: PackageStore) -> None:
        self.database = database
        self.packages = packages

    def molecule_package(self, package_id: str) -> dict:
        descriptor = self.packages.descriptor(package_id)
        if descriptor.kind != "molecules":
            raise ValueError("Expected a Molecules package")
        package_hash = self.packages.fingerprint(package_id)
        path = self.packages._incoming_path(descriptor)
        with self.database.connection() as connection:
            relation = connection.read_parquet(str(path))
            columns = dict(zip(relation.columns, map(str, relation.types), strict=True))
            if columns != {"canonical_smiles": "VARCHAR"}:
                raise ValueError(f"Unsupported Molecules Parquet schema: {columns}")
            connection.execute(
                """
                CREATE OR REPLACE TEMP TABLE _mld_preview_molecules AS
                SELECT trim(canonical_smiles) AS canonical_smiles FROM read_parquet(?)
                """,
                [str(path)],
            )
            row = connection.execute(
                """
                WITH valid AS (
                    SELECT canonical_smiles FROM _mld_preview_molecules
                    WHERE canonical_smiles IS NOT NULL AND length(canonical_smiles) > 0
                ), distinct_valid AS (SELECT DISTINCT canonical_smiles FROM valid)
                SELECT (SELECT count(*) FROM _mld_preview_molecules),
                       (SELECT count(*) FROM valid),
                       (SELECT count(*) FROM distinct_valid),
                       (SELECT count(*) FROM distinct_valid
                        SEMI JOIN Molecules USING (canonical_smiles))
                """
            ).fetchone()
        total, valid, distinct_valid, existing = map(int, row)
        if self.packages.fingerprint(package_id) != package_hash:
            raise ValueError("Molecules package changed during preview")
        return {
            "package_name": descriptor.name,
            "package_hash": package_hash,
            "total_rows": total,
            "valid_rows": valid,
            "new_rows": distinct_valid - existing,
            "existing_rows": existing,
            "duplicate_rows": valid - distinct_valid,
            "invalid_rows": total - valid,
        }

    def annotation_package(self, package_id: str) -> AnnotationPackagePreview:
        descriptor = self.packages.descriptor(package_id)
        if descriptor.kind != "annotations":
            raise ValueError("Expected an Annotation package")
        package_hash = self.packages.fingerprint(package_id)
        token = f"annotation-preview-v1:{descriptor.name}:{package_hash}"
        errors = []
        warnings = []
        missing = sorted(_REQUIRED - set(descriptor.files))
        unexpected = sorted(set(descriptor.files) - _ALLOWED)
        if missing:
            errors.append(f"Missing required package files: {missing}")
        if unexpected:
            errors.append(f"Unexpected package entries: {unexpected}")
        manifest = self._contract(
            package_id, "annotation_manifest.json", AnnotationManifest, errors
        )
        report = self._contract(package_id, "processing_report.json", ProcessingReport, errors)
        attributes, entries = [], []
        metrics = {
            name: 0
            for name in (
                "annotation_rows",
                "invalid_rows",
                "duplicate_annotations",
                "conflicting_duplicate_groups",
                "linkable_molecules",
                "unlinkable_molecules",
                "existing_annotations",
                "expected_inserts",
            )
        }
        if manifest is not None and report is not None and not errors:
            warnings.extend(report.warnings)
            if report.status != "completed":
                errors.append("processing_report.json status is not completed")
            try:
                with self.database.connection() as connection:
                    self._stage_annotations(connection, package_id)
                    attributes, entries, blocked = self._compare_catalog(connection, manifest)
                    metrics = self._annotation_metrics(connection, manifest, blocked)
                    self._validate_rejected(connection, package_id, report, errors)
                    self._source_warnings(connection, manifest, warnings)
            except (duckdb.Error, OSError, ValueError) as exc:
                errors.append(str(exc))
            if any(item.status == "conflict" for item in attributes):
                errors.append("Manifest contains conflicting Attribute definitions")
            if any(item.status == "conflict" for item in entries):
                errors.append("Manifest contains conflicting Entry definitions")
            if metrics["invalid_rows"]:
                errors.append(
                    f"annotations.parquet contains {metrics['invalid_rows']} invalid rows"
                )
            if metrics["conflicting_duplicate_groups"]:
                errors.append("annotations.parquet contains duplicate keys with conflicting values")
            if metrics["annotation_rows"] != report.output_annotations:
                errors.append(
                    "processing_report output_annotations does not match Parquet row count"
                )
            if metrics["duplicate_annotations"] != report.duplicate_rows:
                warnings.append("processing_report duplicate_rows differs from package preview")
        if self.packages.fingerprint(package_id) != package_hash:
            raise ValueError("Annotation package changed during preview")
        return AnnotationPackagePreview(
            package_name=descriptor.name,
            package_hash=package_hash,
            preview_token=token,
            annotation_rows=metrics["annotation_rows"],
            attributes=attributes,
            entries=entries,
            linkable_molecules=metrics["linkable_molecules"],
            unlinkable_molecules=metrics["unlinkable_molecules"],
            duplicate_annotations=metrics["duplicate_annotations"],
            existing_annotations=metrics["existing_annotations"],
            expected_inserts=metrics["expected_inserts"],
            warnings=list(dict.fromkeys(warnings)),
            errors=list(dict.fromkeys(errors)),
            can_import=not errors,
        )

    def _contract(self, package_id, name, model, errors):
        try:
            return model.model_validate(self.packages.read_json(package_id, name))
        except (FileNotFoundError, OSError, ValueError, PydanticValidationError) as exc:
            if name in self.packages.descriptor(package_id).files:
                errors.append(f"Invalid {name}: {exc}")
            return None

    def _stage_annotations(self, connection, package_id):
        descriptor = self.packages.descriptor(package_id)
        path = self.packages._incoming_path(descriptor) / "annotations.parquet"
        relation = connection.read_parquet(str(path))
        columns = dict(zip(relation.columns, map(str, relation.types), strict=True))
        if set(columns) != set(_ANNOTATION_COLUMNS):
            raise ValueError(
                "annotations.parquet columns differ; "
                f"missing={sorted(set(_ANNOTATION_COLUMNS) - set(columns))}, "
                f"extra={sorted(set(columns) - set(_ANNOTATION_COLUMNS))}"
            )
        wrong = {
            key: value
            for key, value in columns.items()
            if value.upper() != _ANNOTATION_COLUMNS[key]
        }
        if wrong:
            raise ValueError(f"annotations.parquet column types differ: {wrong}")
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_preview_annotations AS
            SELECT row_number() OVER () AS source_row_number,
                   trim(canonical_smiles) AS canonical_smiles, attribute_key, entry_key,
                   value_number, value_text, value_boolean FROM read_parquet(?)
            """,
            [str(path)],
        )

    @staticmethod
    def _compare_catalog(connection, manifest):
        stored_attributes = {
            row[0]: row[1:]
            for row in connection.execute(
                """
                SELECT attribute_key, attribute_name, value_type, unit, description
                FROM Attributes
                """
            ).fetchall()
        }
        attributes = []
        for definition in manifest.attributes:
            stored = stored_attributes.get(definition.attribute_key)
            incoming = (
                definition.attribute_name,
                definition.value_type,
                definition.unit,
                definition.description,
            )
            names = ("attribute_name", "value_type", "unit", "description")
            conflicts = (
                []
                if stored is None
                else [
                    name
                    for name, left, right in zip(names, stored, incoming, strict=True)
                    if left != right
                ]
            )
            status = "new" if stored is None else "conflict" if conflicts else "existing"
            attributes.append(
                AttributePreviewItem(definition=definition, status=status, conflicts=conflicts)
            )
        stored_entries = {
            row[0]: row[1:]
            for row in connection.execute(
                """
            SELECT entry.entry_key, attribute.attribute_key, entry.annotation_kind,
                   entry.method_name, entry.method_version, CAST(entry.conditions_json AS VARCHAR),
                   entry.is_mutable, entry.description
            FROM Entries AS entry JOIN Attributes AS attribute USING (attribute_id)
            """
            ).fetchall()
        }
        entries, blocked = [], set()
        for definition in manifest.entries:
            stored = stored_entries.get(definition.entry_key)
            normalized = (
                None if stored is None else (*stored[:4], _canonical_json(stored[4]), *stored[5:])
            )
            incoming = (
                definition.attribute_key,
                definition.annotation_kind,
                definition.method_name,
                definition.method_version,
                _canonical_json(definition.conditions),
                definition.is_mutable,
                definition.description,
            )
            names = (
                "attribute_key",
                "annotation_kind",
                "method_name",
                "method_version",
                "conditions",
                "is_mutable",
                "description",
            )
            conflicts = (
                []
                if normalized is None
                else [
                    name
                    for name, left, right in zip(names, normalized, incoming, strict=True)
                    if left != right
                ]
            )
            status = "new" if stored is None else "conflict" if conflicts else "existing"
            if conflicts:
                blocked.add(definition.entry_key)
            entries.append(
                EntryPreviewItem(definition=definition, status=status, conflicts=conflicts)
            )
        blocked.update(
            entry.definition.entry_key
            for entry in entries
            if any(
                a.definition.attribute_key == entry.definition.attribute_key
                and a.status == "conflict"
                for a in attributes
            )
        )
        return attributes, entries, blocked

    @staticmethod
    def _annotation_metrics(connection, manifest, blocked):
        value_types = {item.attribute_key: item.value_type for item in manifest.attributes}
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_preview_entries (
                entry_key VARCHAR, attribute_key VARCHAR,
                value_type VARCHAR, blocked BOOLEAN
            )
            """
        )
        connection.executemany(
            "INSERT INTO _mld_preview_entries VALUES (?, ?, ?, ?)",
            [
                (
                    item.entry_key,
                    item.attribute_key,
                    value_types[item.attribute_key],
                    item.entry_key in blocked,
                )
                for item in manifest.entries
            ],
        )
        row = connection.execute(
            """
            WITH checked AS (
              SELECT a.*, d.entry_key IS NOT NULL AS declared_entry,
                     d.attribute_key AS declared_attribute, d.value_type,
                     coalesce(d.blocked, true) AS blocked,
                     ((value_number IS NOT NULL)::INTEGER + (value_text IS NOT NULL)::INTEGER +
                      (value_boolean IS NOT NULL)::INTEGER) AS value_count
              FROM _mld_preview_annotations a LEFT JOIN _mld_preview_entries d USING (entry_key)
            ), valid AS (
              SELECT * FROM checked
              WHERE canonical_smiles IS NOT NULL AND length(canonical_smiles)>0
                AND declared_entry AND attribute_key=declared_attribute AND value_count=1
                AND ((value_type='number' AND value_number IS NOT NULL) OR
                     (value_type='text' AND value_text IS NOT NULL) OR
                     (value_type='boolean' AND value_boolean IS NOT NULL))
            ), unique_valid AS (
              SELECT * EXCLUDE (rn) FROM (SELECT *, row_number() OVER (
                PARTITION BY canonical_smiles, entry_key
                ORDER BY source_row_number) rn FROM valid) WHERE rn=1
            ), duplicate_groups AS (
              SELECT canonical_smiles, entry_key, count(*) row_count,
                     count(DISTINCT struct_pack(
                       number:=value_number, text:=value_text,
                       boolean_value:=value_boolean)) value_count
              FROM valid GROUP BY canonical_smiles, entry_key HAVING count(*)>1
            )
            SELECT (SELECT count(*) FROM checked),
              (SELECT count(*) FROM checked
               WHERE canonical_smiles IS NULL OR length(canonical_smiles)=0
                OR NOT declared_entry OR attribute_key!=declared_attribute OR value_count!=1
                OR NOT ((value_type='number' AND value_number IS NOT NULL) OR
                        (value_type='text' AND value_text IS NOT NULL) OR
                        (value_type='boolean' AND value_boolean IS NOT NULL))),
              (SELECT coalesce(sum(row_count-1),0) FROM duplicate_groups),
              (SELECT count(*) FROM duplicate_groups WHERE value_count>1),
              (SELECT count(DISTINCT canonical_smiles) FROM unique_valid
               SEMI JOIN Molecules USING(canonical_smiles)),
              (SELECT count(DISTINCT canonical_smiles) FROM unique_valid
               ANTI JOIN Molecules USING(canonical_smiles)),
              (SELECT count(*) FROM unique_valid c JOIN Molecules m USING(canonical_smiles)
                JOIN Entries e USING(entry_key)
                SEMI JOIN Annotations s
                  ON s.molecule_id=m.molecule_id AND s.entry_id=e.entry_id),
              (SELECT count(*) FROM unique_valid c
               JOIN Molecules m USING(canonical_smiles) WHERE NOT blocked
                AND NOT EXISTS (SELECT 1 FROM Entries e JOIN Annotations s USING(entry_id)
                  WHERE e.entry_key=c.entry_key AND s.molecule_id=m.molecule_id))
            """
        ).fetchone()
        names = (
            "annotation_rows",
            "invalid_rows",
            "duplicate_annotations",
            "conflicting_duplicate_groups",
            "linkable_molecules",
            "unlinkable_molecules",
            "existing_annotations",
            "expected_inserts",
        )
        return dict(zip(names, map(int, row), strict=True))

    def _validate_rejected(self, connection, package_id, report, errors):
        descriptor = self.packages.descriptor(package_id)
        exists = "rejected.parquet" in descriptor.files
        if report.rejected_rows > 0 and not exists:
            errors.append(
                "processing_report declares rejected rows but rejected.parquet is missing"
            )
            return
        if not exists:
            return
        path = self.packages._incoming_path(descriptor) / "rejected.parquet"
        relation = connection.read_parquet(str(path))
        required = {
            "source_row",
            "smiles",
            "output_key",
            "raw_value",
            "error_code",
            "error_message",
        }
        missing = sorted(required - set(relation.columns))
        if missing:
            errors.append(f"rejected.parquet is missing columns: {missing}")
        if int(relation.aggregate("count(*)").fetchone()[0]) != report.rejected_rows:
            errors.append("processing_report rejected_rows does not match rejected.parquet")

    @staticmethod
    def _source_warnings(connection, manifest, warnings):
        keys = sorted({item.source_key for item in manifest.entries if item.source_key})
        if not keys:
            return
        placeholders = ", ".join("?" for _ in keys)
        existing = {
            row[0]
            for row in connection.execute(
                f"SELECT source_key FROM Sources WHERE source_key IN ({placeholders})", keys
            ).fetchall()
        }
        missing = sorted(set(keys) - existing)
        if missing:
            warnings.append(f"Manifest references new Sources: {missing}")


def _canonical_json(value: object) -> str:
    if isinstance(value, str):
        value = json.loads(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
