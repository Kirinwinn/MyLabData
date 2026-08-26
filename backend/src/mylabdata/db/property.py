"""Transactional persistence operations for mutable Property values."""

from typing import Any

import duckdb


def upsert_property_value(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    molecule_id: int,
    entry_id: int,
    value_number: float | None,
    value_text: str | None,
    value_boolean: bool | None,
    source: str,
) -> tuple[bool, Any]:
    """Update one value and append its immutable audit row."""
    old = database_connection.execute(
        """
        SELECT value_number, value_text, value_boolean
        FROM Annotations WHERE molecule_id = ? AND entry_id = ?
        """,
        [molecule_id, entry_id],
    ).fetchone()
    created = old is None
    if created:
        old = (None, None, None)
        database_connection.execute(
            """
            INSERT INTO Annotations (
                molecule_id, entry_id, value_number, value_text, value_boolean
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [molecule_id, entry_id, value_number, value_text, value_boolean],
        )
    else:
        database_connection.execute(
            """
            UPDATE Annotations
            SET value_number = ?, value_text = ?, value_boolean = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE molecule_id = ? AND entry_id = ?
            """,
            [value_number, value_text, value_boolean, molecule_id, entry_id],
        )

    changed_at = database_connection.execute(
        """
        INSERT INTO PropertyChanges (
            molecule_id, entry_id,
            old_value_number, old_value_text, old_value_boolean,
            new_value_number, new_value_text, new_value_boolean,
            change_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING changed_at
        """,
        [
            molecule_id,
            entry_id,
            *old,
            value_number,
            value_text,
            value_boolean,
            source,
        ],
    ).fetchone()[0]
    return created, changed_at
