"""Read-only access to the v3 Attribute, Entry, and catalog relationships."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from access.cache import CacheKey, CacheStore
from access.database import DryDataDatabase

STATISTICS_NAMESPACE = "entry-statistics"


@dataclass(frozen=True, slots=True)
class AttributeRow:
    attribute_id: int
    attribute_key: str
    attribute_name: str
    value_type: str
    unit: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class EntryRow:
    entry_id: int
    attribute_id: int
    entry_key: str
    annotation_kind: str
    method_name: str
    method_version: str | None
    conditions: dict[str, Any]
    is_mutable: bool
    description: str | None


@dataclass(frozen=True, slots=True)
class MoleculeAttributeAnnotationRow:
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


@dataclass(frozen=True, slots=True)
class EntryStatisticsRow:
    attribute_id: int
    entry_id: int
    entry_key: str
    value_type: str
    count: int
    distinct_count: int
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    true_count: int | None = None
    false_count: int | None = None


@dataclass(frozen=True, slots=True)
class EntryIndexRow:
    """One registered entry with its parent attribute and full definition."""

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


@dataclass(frozen=True, slots=True)
class EntryDefinitionRow:
    """The complete registered definition of one entry."""

    entry_id: int
    entry_key: str
    attribute_key: str
    annotation_kind: str
    method_name: str
    method_version: str | None
    conditions: dict[str, Any]
    is_mutable: bool
    description: str | None


class CatalogRepository:
    """Own all v3 SQL needed by catalog Query Jobs."""

    def __init__(self, database: DryDataDatabase, cache: CacheStore | None = None) -> None:
        self.database = database
        self.cache = cache

    def list_attributes(self) -> list[AttributeRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT attribute_id, attribute_key, attribute_name,
                       value_type, unit, description
                FROM Attributes ORDER BY attribute_name, attribute_id
                """
            ).fetchall()
        return [AttributeRow(*row) for row in rows]

    def attribute_by_key(self, attribute_key: str) -> AttributeRow | None:
        """Return one registered Attribute by its stable key, if present."""
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT attribute_id, attribute_key, attribute_name,
                       value_type, unit, description
                FROM Attributes WHERE attribute_key = ?
                """,
                [attribute_key],
            ).fetchone()
        return AttributeRow(*row) if row else None

    def entry_by_key(self, entry_key: str) -> EntryDefinitionRow | None:
        """Return one registered Entry with its complete definition, if present."""
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT entry.entry_id, entry.entry_key, attribute.attribute_key,
                       entry.annotation_kind, entry.method_name, entry.method_version,
                       CAST(entry.conditions_json AS VARCHAR), entry.is_mutable,
                       entry.description
                FROM Entries AS entry
                JOIN Attributes AS attribute USING (attribute_id)
                WHERE entry.entry_key = ?
                """,
                [entry_key],
            ).fetchone()
        if row is None:
            return None
        return EntryDefinitionRow(
            entry_id=int(row[0]),
            entry_key=str(row[1]),
            attribute_key=str(row[2]),
            annotation_kind=str(row[3]),
            method_name=str(row[4]),
            method_version=str(row[5]) if row[5] is not None else None,
            conditions=json.loads(row[6]) if row[6] else {},
            is_mutable=bool(row[7]),
            description=str(row[8]) if row[8] is not None else None,
        )

    def list_entries(self, attribute_id: int) -> list[EntryRow]:
        with self.database.connection() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM Attributes WHERE attribute_id = ?", [attribute_id]
                ).fetchone()
                is None
            ):
                raise KeyError(attribute_id)
            rows = connection.execute(
                """
                SELECT entry_id, attribute_id, entry_key, annotation_kind,
                       method_name, method_version, CAST(conditions_json AS VARCHAR),
                       is_mutable, description
                FROM Entries WHERE attribute_id = ? ORDER BY entry_key
                """,
                [attribute_id],
            ).fetchall()
        return [
            EntryRow(
                entry_id=int(row[0]),
                attribute_id=int(row[1]),
                entry_key=str(row[2]),
                annotation_kind=str(row[3]),
                method_name=str(row[4]),
                method_version=str(row[5]) if row[5] is not None else None,
                conditions=json.loads(row[6]) if row[6] else {},
                is_mutable=bool(row[7]),
                description=str(row[8]) if row[8] is not None else None,
            )
            for row in rows
        ]

    def list_entries_index(self) -> list[EntryIndexRow]:
        """Read every registered entry with its attribute, ordered for pickers."""
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT entry.entry_id, entry.entry_key, attribute.attribute_key,
                       attribute.attribute_name, entry.annotation_kind,
                       entry.method_name, entry.method_version,
                       CAST(entry.conditions_json AS VARCHAR), entry.is_mutable,
                       entry.description
                FROM Entries AS entry
                JOIN Attributes AS attribute USING (attribute_id)
                ORDER BY attribute.attribute_name, entry.entry_key
                """
            ).fetchall()
        return [
            EntryIndexRow(
                entry_id=int(row[0]),
                entry_key=str(row[1]),
                attribute_key=str(row[2]),
                attribute_name=str(row[3]),
                annotation_kind=str(row[4]),
                method_name=str(row[5]),
                method_version=str(row[6]) if row[6] is not None else None,
                conditions=json.loads(row[7]) if row[7] else {},
                is_mutable=bool(row[8]),
                description=str(row[9]) if row[9] is not None else None,
            )
            for row in rows
        ]

    def existing_annotation_pairs(
        self,
        *,
        molecule_ids: list[int],
        entry_ids: list[int],
    ) -> set[tuple[int, int]]:
        """Return which (molecule, entry) pairs already have stored annotations."""
        if not molecule_ids or not entry_ids:
            return set()
        molecule_placeholders = ", ".join("?" for _ in molecule_ids)
        entry_placeholders = ", ".join("?" for _ in entry_ids)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT molecule_id, entry_id FROM Annotations
                WHERE entry_id IN ({entry_placeholders})
                  AND molecule_id IN ({molecule_placeholders})
                """,
                [*entry_ids, *molecule_ids],
            ).fetchall()
        return {(int(row[0]), int(row[1])) for row in rows}

    def molecule_attributes(self, molecule_id: int) -> list[AttributeRow]:
        """Return only Attributes that have Annotations for one Molecule."""
        with self.database.connection() as connection:
            self._require_molecule(connection, molecule_id)
            rows = connection.execute(
                """
                SELECT DISTINCT attribute.attribute_id, attribute.attribute_key,
                       attribute.attribute_name, attribute.value_type,
                       attribute.unit, attribute.description
                FROM Annotations AS annotation
                JOIN Entries AS entry USING (entry_id)
                JOIN Attributes AS attribute USING (attribute_id)
                WHERE annotation.molecule_id = ?
                ORDER BY attribute.attribute_name, attribute.attribute_id
                """,
                [molecule_id],
            ).fetchall()
        return [AttributeRow(*row) for row in rows]

    def molecule_attribute_annotations(
        self, molecule_id: int, attribute_id: int
    ) -> list[MoleculeAttributeAnnotationRow]:
        """Return one Molecule's Annotations for one selected Attribute."""
        with self.database.connection() as connection:
            self._require_molecule(connection, molecule_id)
            if (
                connection.execute(
                    "SELECT 1 FROM Attributes WHERE attribute_id = ?", [attribute_id]
                ).fetchone()
                is None
            ):
                raise KeyError(attribute_id)
            rows = connection.execute(
                """
                SELECT entry.entry_id, entry.entry_key, entry.annotation_kind,
                       entry.method_name, entry.method_version,
                       CAST(entry.conditions_json AS VARCHAR), entry.is_mutable,
                       entry.description, annotation.value_number,
                       annotation.value_text, annotation.value_boolean, annotation.updated_at
                FROM Annotations AS annotation
                JOIN Entries AS entry USING (entry_id)
                WHERE annotation.molecule_id = ? AND entry.attribute_id = ?
                ORDER BY entry.entry_key, annotation.updated_at DESC
                """,
                [molecule_id, attribute_id],
            ).fetchall()
        result = []
        for row in rows:
            value = next(value for value in row[8:11] if value is not None)
            result.append(
                MoleculeAttributeAnnotationRow(
                    entry_id=int(row[0]),
                    entry_key=str(row[1]),
                    annotation_kind=str(row[2]),
                    method_name=str(row[3]),
                    method_version=str(row[4]) if row[4] is not None else None,
                    conditions=json.loads(row[5]) if row[5] else {},
                    is_mutable=bool(row[6]),
                    description=str(row[7]) if row[7] is not None else None,
                    value=value,
                    updated_at=row[11],
                )
            )
        return result

    @staticmethod
    def _require_molecule(connection, molecule_id: int) -> None:
        if (
            connection.execute(
                "SELECT 1 FROM Molecules WHERE molecule_id = ?", [molecule_id]
            ).fetchone()
            is None
        ):
            raise KeyError(molecule_id)

    def counts(self) -> dict[str, int]:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT (SELECT count(*) FROM Molecules),
                       (SELECT count(*) FROM Attributes),
                       (SELECT count(*) FROM Entries),
                       (SELECT count(*) FROM Annotations),
                       (SELECT count(*) FROM Imports)
                """
            ).fetchone()
        names = ("molecules", "attributes", "entries", "annotations", "imports")
        return {name: int(value) for name, value in zip(names, row, strict=True)}

    def attribute_statistics(self, attribute_id: int) -> list[EntryStatisticsRow]:
        with self.database.connection() as connection:
            definitions = connection.execute(
                """
                SELECT entry.entry_id, entry.entry_key, attribute.value_type
                FROM Entries AS entry
                JOIN Attributes AS attribute USING (attribute_id)
                WHERE attribute.attribute_id = ? ORDER BY entry.entry_id
                """,
                [attribute_id],
            ).fetchall()
            if (
                not definitions
                and connection.execute(
                    "SELECT 1 FROM Attributes WHERE attribute_id = ?", [attribute_id]
                ).fetchone()
                is None
            ):
                raise KeyError(attribute_id)
            key = CacheKey(
                namespace=STATISTICS_NAMESPACE,
                payload=f"attribute-{attribute_id}",
                data_revision=self._data_revision(connection),
            )
            cached = self._read_cache(key)
            if cached is not None:
                return [EntryStatisticsRow(**item) for item in cached]
            aggregates = self._aggregate(connection, definitions)
            rows = self._statistics_rows(attribute_id, definitions, aggregates)
        self._write_cache(key, rows)
        return rows

    @staticmethod
    def _data_revision(connection) -> str:
        row = connection.execute(
            "SELECT (SELECT count(*) FROM Annotations), (SELECT count(*) FROM Entries)"
        ).fetchone()
        return f"annotations-{int(row[0])}-entries-{int(row[1])}"

    def _read_cache(self, key: CacheKey) -> list[dict[str, Any]] | None:
        if self.cache is None:
            return None
        try:
            record = self.cache.read(key)
        except OSError:
            return None
        if record is None:
            return None
        items = record.get("items")
        return items if isinstance(items, list) else None

    def _write_cache(self, key: CacheKey, rows: list[EntryStatisticsRow]) -> None:
        if self.cache is None:
            return
        try:
            self.cache.write(key, {"items": [asdict(row) for row in rows]})
        except OSError:
            pass

    @staticmethod
    def _aggregate(connection, definitions: list[tuple]) -> dict[int, tuple]:
        value_type = str(definitions[0][2])
        column = {
            "number": "value_number",
            "text": "value_text",
            "boolean": "value_boolean",
        }[value_type]
        entry_ids = [int(row[0]) for row in definitions]
        placeholders = ", ".join("?" for _ in entry_ids)
        if value_type == "number":
            rows = connection.execute(
                f"""
                SELECT entry_id, count({column}), count(DISTINCT {column}), min({column}),
                       max({column}), avg({column}), median({column}), stddev_samp({column})
                FROM Annotations
                WHERE entry_id IN ({placeholders})
                GROUP BY entry_id
                """,
                entry_ids,
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT entry_id, count({column}), count(DISTINCT {column}),
                       count(*) FILTER (WHERE value_boolean = true),
                       count(*) FILTER (WHERE value_boolean = false)
                FROM Annotations
                WHERE entry_id IN ({placeholders})
                GROUP BY entry_id
                """,
                entry_ids,
            ).fetchall()
        return {int(row[0]): tuple(row[1:]) for row in rows}

    @staticmethod
    def _statistics_rows(
        attribute_id: int,
        definitions: list[tuple],
        aggregates: dict[int, tuple],
    ) -> list[EntryStatisticsRow]:
        value_type = str(definitions[0][2])
        rows = []
        for entry_id, entry_key, _ in definitions:
            values = aggregates.get(int(entry_id))
            if value_type == "number":
                if values is None:
                    values = (0, 0, None, None, None, None, None)
                rows.append(
                    EntryStatisticsRow(
                        attribute_id=attribute_id,
                        entry_id=int(entry_id),
                        entry_key=str(entry_key),
                        value_type=value_type,
                        count=int(values[0]),
                        distinct_count=int(values[1]),
                        min=values[2],
                        max=values[3],
                        mean=values[4],
                        median=values[5],
                        std=values[6],
                    )
                )
            else:
                if values is None:
                    values = (0, 0, 0, 0)
                rows.append(
                    EntryStatisticsRow(
                        attribute_id=attribute_id,
                        entry_id=int(entry_id),
                        entry_key=str(entry_key),
                        value_type=value_type,
                        count=int(values[0]),
                        distinct_count=int(values[1]),
                        true_count=int(values[2]) if value_type == "boolean" else None,
                        false_count=int(values[3]) if value_type == "boolean" else None,
                    )
                )
        return rows
