"""Unpaginated search reads that back spreadsheet export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from access.database import DryDataDatabase
from access.molecules import MoleculeRecord, _record_from_row
from access.search import SearchCondition, SearchRepository

SearchLogic = Literal["and", "or"]


@dataclass(frozen=True, slots=True)
class _ConditionMeta:
    attribute_name: str
    entry_key: str
    unit: str | None


@dataclass(frozen=True, slots=True)
class ExportCondition:
    """One resolved condition with display metadata and its own hit count."""

    attribute_name: str
    entry_key: str
    unit: str | None
    operator: str
    value: Any
    second_value: Any | None
    matched_count: int


@dataclass(frozen=True, slots=True)
class AndExportRows:
    """Molecules matching every condition, with one value column per condition."""

    molecules: tuple[MoleculeRecord, ...]
    values: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class AndExport:
    """Complete AND result set: per-condition stats, intersection total, rows."""

    conditions: tuple[ExportCondition, ...]
    total: int
    rows: AndExportRows


@dataclass(frozen=True, slots=True)
class OrExportSet:
    """One condition's matched molecules with that condition's value."""

    condition_index: int
    molecules: tuple[MoleculeRecord, ...]
    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class OrExport:
    """Complete OR result: per-condition stats, union total, one set per condition."""

    conditions: tuple[ExportCondition, ...]
    total: int
    sets: tuple[OrExportSet, ...]


ExportResult = AndExport | OrExport


class ExportRepository:
    """Read full search result sets with per-condition values for export."""

    def __init__(self, database: DryDataDatabase) -> None:
        self.database = database
        self._search = SearchRepository(database)

    def export(
        self,
        conditions: list[SearchCondition],
        *,
        logic: SearchLogic,
    ) -> ExportResult:
        """Return per-condition statistics and complete rows for one search export."""
        if not conditions:
            raise ValueError("Export requires at least one search condition")
        with self.database.connection() as connection:
            resolved = [self._search._resolve(connection, condition) for condition in conditions]
            metas = [self._describe(connection, entry_id) for entry_id, _, _, _ in resolved]
            counts = self._counts(connection, resolved, logic=logic)
            exported = tuple(
                ExportCondition(
                    attribute_name=meta.attribute_name,
                    entry_key=meta.entry_key,
                    unit=meta.unit,
                    operator=condition.operator,
                    value=condition.value,
                    second_value=condition.second_value,
                    matched_count=count,
                )
                for condition, meta, count in zip(conditions, metas, counts)
            )
            if logic == "and":
                rows = self._and_rows(connection, resolved)
                return AndExport(conditions=exported, total=counts[-1], rows=rows)
            sets = self._or_sets(connection, resolved)
            return OrExport(conditions=exported, total=counts[-1], sets=sets)

    def _ctes(
        self,
        resolved: list[tuple[int, str, str, tuple[Any, ...]]],
        *,
        limit: int | None = None,
    ) -> tuple[str, list[Any]]:
        selected = resolved if limit is None else resolved[:limit]
        ctes: list[str] = []
        parameters: list[Any] = []
        for index, (entry_id, column, operator, values) in enumerate(selected):
            predicate, predicate_values = self._search._predicate(column, operator, values)
            ctes.append(
                f"condition_{index} AS (SELECT molecule_id, any_value({column}) AS value_{index} "
                f"FROM Annotations WHERE entry_id = ? AND {predicate} GROUP BY molecule_id)"
            )
            parameters.append(entry_id)
            parameters.extend(predicate_values)
        return ", ".join(ctes), parameters

    @staticmethod
    def _matched_sql(logic: SearchLogic, condition_count: int) -> str:
        set_operator = " INTERSECT " if logic == "and" else " UNION "
        return set_operator.join(
            f"SELECT molecule_id FROM condition_{index}" for index in range(condition_count)
        )

    def _counts(
        self,
        connection,
        resolved: list[tuple[int, str, str, tuple[Any, ...]]],
        *,
        logic: SearchLogic,
    ) -> tuple[int, ...]:
        ctes, parameters = self._ctes(resolved)
        columns = ", ".join(
            f"(SELECT count(*) FROM condition_{index})" for index in range(len(resolved))
        )
        row = connection.execute(
            f"WITH {ctes}, matched AS ({self._matched_sql(logic, len(resolved))}) "
            f"SELECT {columns}, (SELECT count(*) FROM matched)",
            parameters,
        ).fetchone()
        return tuple(int(value) for value in row)

    def _and_rows(
        self,
        connection,
        resolved: list[tuple[int, str, str, tuple[Any, ...]]],
    ) -> AndExportRows:
        ctes, parameters = self._ctes(resolved)
        value_columns = ", ".join(
            f"condition_{index}.value_{index}" for index in range(len(resolved))
        )
        joins = " ".join(
            f"JOIN condition_{index} USING (molecule_id)" for index in range(len(resolved))
        )
        rows = connection.execute(
            f"""
            WITH {ctes}, matched AS ({self._matched_sql("and", len(resolved))})
            SELECT molecule.molecule_id, molecule.lab_id, molecule.canonical_smiles,
                   molecule.channel, epoch_ms(molecule.created_at), {value_columns}
            FROM Molecules AS molecule
            JOIN matched USING (molecule_id)
            {joins}
            ORDER BY molecule.molecule_id
            """,
            parameters,
        ).fetchall()
        return AndExportRows(
            molecules=tuple(_record_from_row(row) for row in rows),
            values=tuple(tuple(row[5 + index] for index in range(len(resolved))) for row in rows),
        )

    def _or_sets(
        self,
        connection,
        resolved: list[tuple[int, str, str, tuple[Any, ...]]],
    ) -> tuple[OrExportSet, ...]:
        sets: list[OrExportSet] = []
        for index in range(len(resolved)):
            ctes, parameters = self._ctes(resolved, limit=index + 1)
            rows = connection.execute(
                f"""
                WITH {ctes}
                SELECT molecule.molecule_id, molecule.lab_id, molecule.canonical_smiles,
                       molecule.channel, epoch_ms(molecule.created_at),
                       condition_{index}.value_{index}
                FROM Molecules AS molecule
                JOIN condition_{index} USING (molecule_id)
                ORDER BY molecule.molecule_id
                """,
                parameters,
            ).fetchall()
            sets.append(
                OrExportSet(
                    condition_index=index,
                    molecules=tuple(_record_from_row(row) for row in rows),
                    values=tuple(row[5] for row in rows),
                )
            )
        return tuple(sets)

    @staticmethod
    def _describe(connection, entry_id: int) -> _ConditionMeta:
        row = connection.execute(
            """
            SELECT attribute.attribute_name, entry.entry_key, attribute.unit
            FROM Entries AS entry
            JOIN Attributes AS attribute USING (attribute_id)
            WHERE entry.entry_id = ?
            """,
            [entry_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"Entry {entry_id} does not resolve to one catalog definition")
        return _ConditionMeta(
            attribute_name=str(row[0]),
            entry_key=str(row[1]),
            unit=str(row[2]) if row[2] is not None else None,
        )
