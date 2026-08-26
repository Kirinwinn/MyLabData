"""Type-safe multi-Entry molecule search independent of HTTP."""

from time import perf_counter

from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import ValidationError
from mylabdata.db.connection import connection
from mylabdata.db.search import ResolvedSearchCondition, search_molecule_rows
from mylabdata.schemas.catalog import (
    MoleculeSummary,
    SearchCondition,
    SearchRequest,
    SearchResult,
)

ALLOWED_OPERATORS = {
    "number": {"eq", "ne", "lt", "lte", "gt", "gte", "between"},
    "text": {"eq", "ne", "contains", "starts_with", "ends_with"},
    "boolean": {"eq", "ne"},
}
VALUE_COLUMNS = {
    "number": "value_number",
    "text": "value_text",
    "boolean": "value_boolean",
}


def search_molecules(
    request: SearchRequest,
    settings: Settings | None = None,
) -> SearchResult:
    """Validate catalog/type contracts and execute one set-based search."""
    started = perf_counter()
    resolved_settings = settings or get_settings()
    with connection(resolved_settings) as database_connection:
        conditions = [
            _resolve_condition(database_connection, condition)
            for condition in request.conditions
        ]
        rows = search_molecule_rows(
            database_connection,
            conditions,
            logic=request.logic,
            limit=request.limit,
            offset=request.offset,
        )
    columns = ("molecule_id", "lab_id", "canonical_smiles", "created_at")
    molecules = [
        MoleculeSummary(**dict(zip(columns, row, strict=True)))
        for row in rows
    ]
    return SearchResult(
        molecules=molecules,
        elapsed_ms=(perf_counter() - started) * 1000,
        limit=request.limit,
        offset=request.offset,
    )


def _resolve_condition(database_connection, condition: SearchCondition):
    attribute_clause = (
        "attribute.attribute_id = ?"
        if condition.attribute_id is not None
        else "attribute.attribute_key = ?"
    )
    attribute_value = condition.attribute_id or condition.attribute_key
    entry_clause = (
        "entry.entry_id = ?"
        if condition.entry_id is not None
        else "entry.entry_key = ?"
    )
    entry_value = condition.entry_id or condition.entry_key
    row = database_connection.execute(
        f"""
        SELECT entry.entry_id, attribute.value_type
        FROM Entries AS entry
        JOIN Attributes AS attribute USING (attribute_id)
        WHERE {attribute_clause} AND {entry_clause}
        """,
        [attribute_value, entry_value],
    ).fetchone()
    if row is None:
        raise ValidationError("Attribute and Entry do not identify one catalog definition")
    entry_id, value_type = row
    if condition.operator not in ALLOWED_OPERATORS[value_type]:
        raise ValidationError(
            f"Operator {condition.operator!r} is invalid for {value_type} values"
        )
    values = _validated_values(condition, value_type)
    return ResolvedSearchCondition(
        entry_id=int(entry_id),
        value_column=VALUE_COLUMNS[value_type],
        operator=condition.operator,
        values=values,
    )


def _validated_values(condition: SearchCondition, value_type: str) -> tuple:
    if value_type == "number":
        if isinstance(condition.value, bool) or not isinstance(condition.value, (int, float)):
            raise ValidationError("Numeric search values must be int or float")
        first = float(condition.value)
        if condition.operator == "between":
            second_value = condition.second_value
            if isinstance(second_value, bool) or not isinstance(second_value, (int, float)):
                raise ValidationError("between requires a numeric second_value")
            second = float(second_value)
            if first > second:
                raise ValidationError("between lower bound must not exceed upper bound")
            return first, second
        if condition.second_value is not None:
            raise ValidationError("second_value is only valid with between")
        return (first,)
    if value_type == "text":
        if not isinstance(condition.value, str):
            raise ValidationError("Text search value must be a string")
    elif type(condition.value) is not bool:
        raise ValidationError("Boolean search value must be true or false")
    if condition.second_value is not None:
        raise ValidationError("second_value is only valid with between")
    return (condition.value,)
