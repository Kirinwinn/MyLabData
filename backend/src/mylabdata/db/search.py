"""Parameterized set-intersection queries for Annotation search."""

from dataclasses import dataclass
from typing import Any, Literal

import duckdb


@dataclass(frozen=True)
class ResolvedSearchCondition:
    entry_id: int
    value_column: Literal["value_number", "value_text", "value_boolean"]
    operator: str
    values: tuple[Any, ...]


def search_molecule_rows(
    database_connection: duckdb.DuckDBPyConnection,
    conditions: list[ResolvedSearchCondition],
    *,
    logic: Literal["and", "or"],
    limit: int,
    offset: int,
) -> list[tuple]:
    """Return Molecules matching all or any resolved Entry predicates."""
    ctes: list[str] = []
    parameters: list[Any] = []
    for index, condition in enumerate(conditions):
        predicate, predicate_parameters = _predicate(condition)
        ctes.append(
            f"""
            condition_{index} AS (
                SELECT molecule_id
                FROM Annotations
                WHERE entry_id = ? AND {predicate}
            )
            """
        )
        parameters.append(condition.entry_id)
        parameters.extend(predicate_parameters)

    set_operator = " INTERSECT " if logic == "and" else " UNION "
    matched = set_operator.join(
        f"SELECT molecule_id FROM condition_{index}"
        for index in range(len(conditions))
    )
    parameters.extend([limit, offset])
    return database_connection.execute(
        f"""
        WITH {', '.join(ctes)},
        matched AS ({matched})
        SELECT molecule.molecule_id, molecule.lab_id,
               molecule.canonical_smiles, molecule.created_at
        FROM Molecules AS molecule
        SEMI JOIN matched USING (molecule_id)
        ORDER BY molecule.molecule_id
        LIMIT ? OFFSET ?
        """,
        parameters,
    ).fetchall()


def _predicate(
    condition: ResolvedSearchCondition,
) -> tuple[str, list[Any]]:
    column = condition.value_column
    operator = condition.operator
    if operator == "between":
        return f"{column} BETWEEN ? AND ?", list(condition.values)
    if operator == "contains":
        return f"contains({column}, ?)", list(condition.values)
    if operator == "starts_with":
        return f"starts_with({column}, ?)", list(condition.values)
    if operator == "ends_with":
        return f"ends_with({column}, ?)", list(condition.values)
    sql_operator = {
        "eq": "=",
        "ne": "!=",
        "lt": "<",
        "lte": "<=",
        "gt": ">",
        "gte": ">=",
    }[operator]
    return f"{column} {sql_operator} ?", list(condition.values)
