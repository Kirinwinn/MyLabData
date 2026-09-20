"""Third-version DryData access for the Molecules table."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb

from access.database import DryDataDatabase


@dataclass(frozen=True, slots=True)
class MoleculeRecord:
    molecule_id: int
    lab_id: str
    canonical_smiles: str
    channel: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class NewMolecule:
    """A fully assigned molecule row ready for an explicit database transaction."""

    molecule_id: int
    lab_id: str
    canonical_smiles: str
    channel: str | None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EntryResultFilter:
    """Restrict molecules to those with (or without) one entry's annotations."""

    entry_id: int
    has_results: bool


@dataclass(frozen=True, slots=True)
class MoleculePage:
    """One page of molecules plus the total count under the same filter."""

    records: list[MoleculeRecord]
    total: int


class MoleculeRepository:
    """Read and write Molecules through the unified access layer."""

    def __init__(self, database: DryDataDatabase) -> None:
        self.database = database

    def get(self, molecule_id: int) -> MoleculeRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT molecule_id, lab_id, canonical_smiles, channel, epoch_ms(created_at)
                FROM Molecules
                WHERE molecule_id = ?
                """,
                [molecule_id],
            ).fetchone()
        return _record_from_row(row) if row else None

    def find_by_lab_id(self, lab_id: str) -> MoleculeRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT molecule_id, lab_id, canonical_smiles, channel, epoch_ms(created_at)
                FROM Molecules
                WHERE lab_id = ?
                """,
                [lab_id],
            ).fetchone()
        return _record_from_row(row) if row else None

    def molecule_ids_for_smiles(self, smiles: Iterable[str]) -> dict[str, int]:
        """Return the molecule_id for each input SMILES already present."""
        values = tuple(dict.fromkeys(smiles))
        if not values:
            return {}
        placeholders = ", ".join("?" for _ in values)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT canonical_smiles, molecule_id FROM Molecules
                WHERE canonical_smiles IN ({placeholders})
                """,
                list(values),
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def list_smiles(self, entry_filter: EntryResultFilter | None = None) -> list[str]:
        """Return every canonical SMILES ordered by molecule_id, optionally filtered."""
        where_parts: list[str] = []
        parameters: list[object] = []
        if entry_filter is not None:
            operator = "EXISTS" if entry_filter.has_results else "NOT EXISTS"
            where_parts.append(
                f"{operator} (SELECT 1 FROM Annotations AS annotation "
                f"WHERE annotation.molecule_id = Molecules.molecule_id "
                f"AND annotation.entry_id = ?)"
            )
            parameters.append(entry_filter.entry_id)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT canonical_smiles FROM Molecules {where} ORDER BY molecule_id",
                parameters,
            ).fetchall()
        return [str(row[0]) for row in rows]

    def find_by_smiles(self, canonical_smiles: str) -> MoleculeRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT molecule_id, lab_id, canonical_smiles, channel, epoch_ms(created_at)
                FROM Molecules
                WHERE canonical_smiles = ?
                """,
                [canonical_smiles],
            ).fetchone()
        return _record_from_row(row) if row else None

    def existing_smiles(self, smiles: Iterable[str]) -> set[str]:
        """Return input SMILES already present in the database."""
        values = tuple(dict.fromkeys(smiles))
        if not values:
            return set()
        placeholders = ", ".join("?" for _ in values)
        with self.database.connection() as connection:
            rows = connection.execute(
                (
                    "SELECT canonical_smiles FROM Molecules "
                    f"WHERE canonical_smiles IN ({placeholders})"
                ),
                list(values),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def list_page(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
        entry_filter: EntryResultFilter | None = None,
    ) -> MoleculePage:
        """Read a stable page of molecules for ordinary v3 Query Jobs."""
        where_parts: list[str] = []
        where_parameters: list[object] = []
        if query:
            pattern = f"%{query}%"
            where_parts.append("(lab_id ILIKE ? OR canonical_smiles ILIKE ?)")
            where_parameters.extend((pattern, pattern))
        if entry_filter is not None:
            operator = "EXISTS" if entry_filter.has_results else "NOT EXISTS"
            where_parts.append(
                f"{operator} (SELECT 1 FROM Annotations AS annotation "
                f"WHERE annotation.molecule_id = Molecules.molecule_id "
                f"AND annotation.entry_id = ?)"
            )
            where_parameters.append(entry_filter.entry_id)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT molecule_id, lab_id, canonical_smiles, channel, epoch_ms(created_at)
                FROM Molecules
                {where}
                ORDER BY molecule_id
                LIMIT ? OFFSET ?
                """,
                [*where_parameters, limit, offset],
            ).fetchall()
            total = int(
                connection.execute(
                    f"SELECT count(*) FROM Molecules {where}", where_parameters
                ).fetchone()[0]
            )
        return MoleculePage(
            records=[_record_from_row(row) for row in rows],
            total=total,
        )

    def insert_many(
        self,
        connection: duckdb.DuckDBPyConnection,
        molecules: Iterable[NewMolecule],
    ) -> int:
        """Insert caller-validated molecules into an existing transaction."""
        rows = [
            (
                item.molecule_id,
                item.lab_id,
                item.canonical_smiles,
                item.channel,
                item.created_at,
            )
            for item in molecules
        ]
        if not rows:
            return 0
        connection.executemany(
            """
            INSERT INTO Molecules (
                molecule_id, lab_id, canonical_smiles, channel, created_at
            ) VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            rows,
        )
        return len(rows)


def _record_from_row(row: tuple) -> MoleculeRecord:
    return MoleculeRecord(
        molecule_id=int(row[0]),
        lab_id=str(row[1]),
        canonical_smiles=str(row[2]),
        channel=str(row[3]) if row[3] is not None else None,
        created_at=(
            datetime.fromtimestamp(int(row[4]) / 1000, tz=UTC) if row[4] is not None else None
        ),
    )
