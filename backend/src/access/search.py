"""Type-aware, parameterized molecule search for the v3 schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from access.database import DryDataDatabase
from access.molecules import MoleculeRecord


@dataclass(frozen=True, slots=True)
class SearchCondition:
    attribute_id: int | None
    attribute_key: str | None
    entry_id: int | None
    entry_key: str | None
    operator: str
    value: Any
    second_value: Any | None = None


@dataclass(frozen=True, slots=True)
class SearchPage:
    records: list[MoleculeRecord]
    total: int


class SearchRepository:
    """Resolve catalog identifiers and execute set-based v3 searches."""

    _allowed = {
        "number": {"eq", "ne", "lt", "lte", "gt", "gte", "between"},
        "text": {"eq", "ne", "contains", "starts_with", "ends_with"},
        "boolean": {"eq", "ne"},
    }
    _columns = {"number": "value_number", "text": "value_text", "boolean": "value_boolean"}

    def __init__(self, database: DryDataDatabase) -> None:
        self.database = database

    def search(
        self,
        conditions: list[SearchCondition],
        *,
        logic: Literal["and", "or"],
        limit: int,
        offset: int,
    ) -> SearchPage:
        with self.database.connection() as connection:
            resolved = [self._resolve(connection, condition) for condition in conditions]
            ctes, parameters = [], []
            for index, (entry_id, column, operator, values) in enumerate(resolved):
                predicate, predicate_values = self._predicate(column, operator, values)
                ctes.append(
                    f"condition_{index} AS (SELECT molecule_id FROM Annotations "
                    f"WHERE entry_id = ? AND {predicate})"
                )
                parameters.append(entry_id)
                parameters.extend(predicate_values)
            set_operator = " INTERSECT " if logic == "and" else " UNION "
            matched = set_operator.join(
                f"SELECT molecule_id FROM condition_{index}" for index in range(len(resolved))
            )
            cte = f"WITH {', '.join(ctes)}, matched AS ({matched})"
            total = int(
                connection.execute(f"{cte} SELECT count(*) FROM matched", parameters).fetchone()[0]
            )
            page_parameters = [*parameters, limit, offset]
            rows = connection.execute(
                f"""
                {cte}
                SELECT molecule.molecule_id, molecule.lab_id, molecule.canonical_smiles,
                       molecule.channel, epoch_ms(molecule.created_at)
                FROM Molecules AS molecule SEMI JOIN matched USING (molecule_id)
                ORDER BY molecule.molecule_id LIMIT ? OFFSET ?
                """,
                page_parameters,
            ).fetchall()
        return SearchPage(
            records=[
                MoleculeRecord(
                    int(row[0]),
                    str(row[1]),
                    str(row[2]),
                    row[3],
                    datetime.fromtimestamp(int(row[4]) / 1000, tz=UTC)
                    if row[4] is not None
                    else None,
                )
                for row in rows
            ],
            total=total,
        )

    def _resolve(self, connection, condition: SearchCondition):
        attribute_clause = (
            "attribute.attribute_id = ?"
            if condition.attribute_id
            else "attribute.attribute_key = ?"
        )
        attribute_value = condition.attribute_id or condition.attribute_key
        entry_clause = "entry.entry_id = ?" if condition.entry_id else "entry.entry_key = ?"
        entry_value = condition.entry_id or condition.entry_key
        row = connection.execute(
            f"""
            SELECT entry.entry_id, attribute.value_type FROM Entries AS entry
            JOIN Attributes AS attribute USING (attribute_id)
            WHERE {attribute_clause} AND {entry_clause}
            """,
            [attribute_value, entry_value],
        ).fetchone()
        if row is None:
            raise ValueError("Attribute and Entry do not identify one catalog definition")
        entry_id, value_type = int(row[0]), str(row[1])
        if condition.operator not in self._allowed[value_type]:
            raise ValueError(f"Operator {condition.operator!r} is invalid for {value_type} values")
        return (
            entry_id,
            self._columns[value_type],
            condition.operator,
            self._values(condition, value_type),
        )

    @staticmethod
    def _values(condition: SearchCondition, value_type: str) -> tuple[Any, ...]:
        if value_type == "number":
            if isinstance(condition.value, bool) or not isinstance(condition.value, (int, float)):
                raise ValueError("Numeric search values must be int or float")
            first = float(condition.value)
            if condition.operator == "between":
                second = condition.second_value
                if isinstance(second, bool) or not isinstance(second, (int, float)):
                    raise ValueError("between requires a numeric second_value")
                if first > float(second):
                    raise ValueError("between lower bound must not exceed upper bound")
                return first, float(second)
        elif value_type == "text" and not isinstance(condition.value, str):
            raise ValueError("Text search value must be a string")
        elif value_type == "boolean" and type(condition.value) is not bool:
            raise ValueError("Boolean search value must be true or false")
        if condition.second_value is not None:
            raise ValueError("second_value is only valid with between")
        return (condition.value,)

    @staticmethod
    def _predicate(column: str, operator: str, values: tuple[Any, ...]):
        if operator == "between":
            return f"{column} BETWEEN ? AND ?", list(values)
        if operator in {"contains", "starts_with", "ends_with"}:
            return f"{operator}({column}, ?)", list(values)
        sql_operator = {"eq": "=", "ne": "!=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}[
            operator
        ]
        return f"{column} {sql_operator} ?", list(values)
