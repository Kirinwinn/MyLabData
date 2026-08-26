"""Type-safe mutation of explicitly mutable Property Entries."""

import duckdb

from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import ConflictError, DatabaseError, ValidationError
from mylabdata.db.connection import connection
from mylabdata.db.property import upsert_property_value
from mylabdata.schemas.catalog import PropertyUpdateRequest, PropertyUpdateResult


def update_property(
    molecule_id: int,
    entry_id: int,
    request: PropertyUpdateRequest,
    settings: Settings | None = None,
) -> PropertyUpdateResult:
    """Validate and atomically update one mutable Property Annotation."""
    resolved_settings = settings or get_settings()
    source = request.source.strip()
    if not source:
        raise ValidationError("Property update source must not be blank")
    try:
        with connection(resolved_settings) as database_connection:
            database_connection.execute("BEGIN TRANSACTION")
            try:
                if database_connection.execute(
                    "SELECT 1 FROM Molecules WHERE molecule_id = ?",
                    [molecule_id],
                ).fetchone() is None:
                    raise KeyError(f"Molecule {molecule_id} does not exist")
                entry = database_connection.execute(
                    """
                    SELECT attribute.value_type, entry.annotation_kind,
                           entry.is_mutable
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
                    raise ConflictError(
                        "Only Entries with annotation_kind='property' and "
                        "is_mutable=true may be changed"
                    )
                values = _validated_property_values(request, value_type)
                created, changed_at = upsert_property_value(
                    database_connection,
                    molecule_id=molecule_id,
                    entry_id=entry_id,
                    value_number=values[0],
                    value_text=values[1],
                    value_boolean=values[2],
                    source=source,
                )
                database_connection.execute("COMMIT")
            except Exception:
                database_connection.execute("ROLLBACK")
                raise
    except (KeyError, ConflictError, ValidationError):
        raise
    except duckdb.Error as exc:
        raise DatabaseError(f"Property update rolled back: {exc}") from exc

    return PropertyUpdateResult(
        molecule_id=molecule_id,
        entry_id=entry_id,
        value_number=values[0],
        value_text=values[1],
        value_boolean=values[2],
        source=source,
        created=created,
        updated_at=changed_at,
    )


def _validated_property_values(
    request: PropertyUpdateRequest,
    value_type: str,
) -> tuple[float | None, str | None, bool | None]:
    supplied_type = (
        "number"
        if request.value_number is not None
        else "text"
        if request.value_text is not None
        else "boolean"
    )
    if supplied_type != value_type:
        raise ValidationError(
            f"Entry requires {value_type!r}, received {supplied_type!r}"
        )
    return request.value_number, request.value_text, request.value_boolean
