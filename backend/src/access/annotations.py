"""Third-version DryData access for Annotations and their catalog definitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import duckdb

from access.database import DryDataDatabase


@dataclass(frozen=True, slots=True)
class AnnotationRecord:
    molecule_id: int
    entry_id: int
    value_number: float | None
    value_text: str | None
    value_boolean: bool | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class AnnotationWrite:
    molecule_id: int
    entry_id: int
    value_number: float | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        count = sum(
            value is not None for value in (self.value_number, self.value_text, self.value_boolean)
        )
        if count != 1:
            raise ValueError("An Annotation must contain exactly one value")


@dataclass(frozen=True, slots=True)
class PropertyWriteResult:
    """Result of one mutable Property Annotation upsert."""

    created: bool
    updated_at: datetime | None


class AnnotationRepository:
    """Access Annotation values without exposing SQL to the business layer."""

    def __init__(self, database: DryDataDatabase) -> None:
        self.database = database

    def for_molecule(self, molecule_id: int) -> list[AnnotationRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT molecule_id, entry_id, value_number, value_text, value_boolean,
                       created_at, updated_at
                FROM Annotations
                WHERE molecule_id = ?
                ORDER BY entry_id
                """,
                [molecule_id],
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def for_entry_range(
        self,
        entry_id: int,
        lower: float,
        upper: float,
        *,
        limit: int = 100,
    ) -> list[AnnotationRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT molecule_id, entry_id, value_number, value_text, value_boolean,
                       created_at, updated_at
                FROM Annotations
                WHERE entry_id = ? AND value_number BETWEEN ? AND ?
                LIMIT ?
                """,
                [entry_id, lower, upper, limit],
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def insert_many(
        self,
        connection: duckdb.DuckDBPyConnection,
        annotations: Iterable[AnnotationWrite],
    ) -> int:
        """Insert caller-validated Annotation rows into an existing transaction."""
        rows = [
            (
                item.molecule_id,
                item.entry_id,
                item.value_number,
                item.value_text,
                item.value_boolean,
                item.created_at,
                item.updated_at,
            )
            for item in annotations
        ]
        if not rows:
            return 0
        connection.executemany(
            """
            INSERT INTO Annotations (
                molecule_id, entry_id, value_number, value_text, value_boolean,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP),
                COALESCE(?, CURRENT_TIMESTAMP)
            )
            """,
            rows,
        )
        return len(rows)

    def upsert_mutable_property(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        molecule_id: int,
        entry_id: int,
        value_number: float | None,
        value_text: str | None,
        value_boolean: bool | None,
    ) -> PropertyWriteResult:
        """Validate and write one mutable Property entirely inside the access layer."""
        if (
            connection.execute(
                "SELECT 1 FROM Molecules WHERE molecule_id = ?", [molecule_id]
            ).fetchone()
            is None
        ):
            raise KeyError(f"Molecule {molecule_id} does not exist")
        entry = connection.execute(
            """
            SELECT attribute.value_type, entry.annotation_kind, entry.is_mutable
            FROM Entries AS entry
            JOIN Attributes AS attribute USING (attribute_id)
            WHERE entry.entry_id = ?
            """,
            [entry_id],
        ).fetchone()
        if entry is None:
            raise KeyError(f"Entry {entry_id} does not exist")
        value_type, annotation_kind, is_mutable = entry
        if annotation_kind != "property" or not is_mutable:
            raise ValueError("Only mutable Property Entries may be changed")
        supplied_type = (
            "number"
            if value_number is not None
            else "text"
            if value_text is not None
            else "boolean"
        )
        if supplied_type != value_type:
            raise ValueError(f"Entry requires {value_type!r}, received {supplied_type!r}")

        existing = connection.execute(
            """
            SELECT 1 FROM Annotations
            WHERE molecule_id = ? AND entry_id = ?
            """,
            [molecule_id, entry_id],
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO Annotations (
                    molecule_id, entry_id, value_number, value_text, value_boolean,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                [molecule_id, entry_id, value_number, value_text, value_boolean],
            )
            created = True
        else:
            connection.execute(
                """
                UPDATE Annotations
                SET value_number = ?, value_text = ?, value_boolean = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE molecule_id = ? AND entry_id = ?
                """,
                [value_number, value_text, value_boolean, molecule_id, entry_id],
            )
            created = False
        updated_at = connection.execute(
            """
            SELECT updated_at FROM Annotations
            WHERE molecule_id = ? AND entry_id = ?
            """,
            [molecule_id, entry_id],
        ).fetchone()[0]
        return PropertyWriteResult(created=created, updated_at=updated_at)


def _record_from_row(row: tuple) -> AnnotationRecord:
    return AnnotationRecord(
        molecule_id=int(row[0]),
        entry_id=int(row[1]),
        value_number=float(row[2]) if row[2] is not None else None,
        value_text=str(row[3]) if row[3] is not None else None,
        value_boolean=bool(row[4]) if row[4] is not None else None,
        created_at=row[5],
        updated_at=row[6],
    )
