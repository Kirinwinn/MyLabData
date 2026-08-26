"""Read-only service operations used by the FastAPI catalog layer."""

import json

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.schemas.catalog import (
    AttributeRecord,
    AttributeStatistics,
    DatabaseStats,
    EntryRecord,
    ImportRecord,
    MoleculeAnnotation,
    MoleculeDetail,
    MoleculeSummary,
)


def read_imports(settings: Settings, *, limit: int, offset: int) -> list[ImportRecord]:
    with connection(settings) as database_connection:
        rows = database_connection.execute(
            f"{_IMPORT_SELECT} ORDER BY import_id DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
    return [ImportRecord(**dict(zip(_IMPORT_COLUMNS, row, strict=True))) for row in rows]


def read_import(settings: Settings, import_id: int) -> ImportRecord:
    with connection(settings) as database_connection:
        row = database_connection.execute(
            f"{_IMPORT_SELECT} WHERE import_id = ?",
            [import_id],
        ).fetchone()
    if row is None:
        raise KeyError(import_id)
    return ImportRecord(**dict(zip(_IMPORT_COLUMNS, row, strict=True)))


def read_molecules(
    settings: Settings,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> list[MoleculeSummary]:
    where = ""
    parameters: list[object] = []
    if query:
        where = "WHERE lab_id ILIKE ? OR canonical_smiles ILIKE ?"
        pattern = f"%{query}%"
        parameters.extend([pattern, pattern])
    parameters.extend([limit, offset])
    with connection(settings) as database_connection:
        rows = database_connection.execute(
            f"""
            SELECT molecule_id, lab_id, canonical_smiles, created_at
            FROM Molecules {where}
            ORDER BY molecule_id LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
    columns = ("molecule_id", "lab_id", "canonical_smiles", "created_at")
    return [
        MoleculeSummary(**dict(zip(columns, row, strict=True)))
        for row in rows
    ]


def read_molecule(settings: Settings, molecule_id: int) -> MoleculeDetail:
    with connection(settings) as database_connection:
        molecule = database_connection.execute(
            """
            SELECT molecule_id, lab_id, canonical_smiles, created_at
            FROM Molecules WHERE molecule_id = ?
            """,
            [molecule_id],
        ).fetchone()
        if molecule is None:
            raise KeyError(molecule_id)
        rows = database_connection.execute(
            """
            SELECT attribute.attribute_key, entry.entry_id, entry.entry_key,
                   annotation.value_number, annotation.value_text,
                   annotation.value_boolean, annotation.updated_at
            FROM Annotations AS annotation
            JOIN Entries AS entry USING (entry_id)
            JOIN Attributes AS attribute USING (attribute_id)
            WHERE annotation.molecule_id = ?
            ORDER BY attribute.attribute_key, entry.entry_key
            """,
            [molecule_id],
        ).fetchall()
    annotations = [
        MoleculeAnnotation(
            attribute_key=row[0],
            entry_id=row[1],
            entry_key=row[2],
            value=next(value for value in row[3:6] if value is not None),
            updated_at=row[6],
        )
        for row in rows
    ]
    return MoleculeDetail(
        molecule_id=molecule[0],
        lab_id=molecule[1],
        canonical_smiles=molecule[2],
        created_at=molecule[3],
        annotations=annotations,
    )


def find_molecule_by_lab_id(settings: Settings, lab_id: str) -> MoleculeDetail:
    """Return the molecule identified by its exact stable Lab ID."""
    with connection(settings) as database_connection:
        row = database_connection.execute(
            "SELECT molecule_id FROM Molecules WHERE lab_id = ?",
            [lab_id],
        ).fetchone()
    if row is None:
        raise KeyError(lab_id)
    return read_molecule(settings, int(row[0]))


def find_molecule_by_smiles(
    settings: Settings,
    canonical_smiles: str,
) -> MoleculeDetail:
    """Return the molecule identified by exact canonical SMILES."""
    with connection(settings) as database_connection:
        row = database_connection.execute(
            "SELECT molecule_id FROM Molecules WHERE canonical_smiles = ?",
            [canonical_smiles],
        ).fetchone()
    if row is None:
        raise KeyError(canonical_smiles)
    return read_molecule(settings, int(row[0]))


def read_attributes(settings: Settings) -> list[AttributeRecord]:
    with connection(settings) as database_connection:
        rows = database_connection.execute(
            """
            SELECT attribute_id, attribute_key, attribute_name,
                   value_type, unit, description
            FROM Attributes ORDER BY attribute_name, attribute_id
            """
        ).fetchall()
    columns = (
        "attribute_id",
        "attribute_key",
        "attribute_name",
        "value_type",
        "unit",
        "description",
    )
    return [
        AttributeRecord(**dict(zip(columns, row, strict=True)))
        for row in rows
    ]


def read_entries(settings: Settings, attribute_id: int) -> list[EntryRecord]:
    with connection(settings) as database_connection:
        exists = database_connection.execute(
            "SELECT 1 FROM Attributes WHERE attribute_id = ?",
            [attribute_id],
        ).fetchone()
        if exists is None:
            raise KeyError(attribute_id)
        rows = database_connection.execute(
            """
            SELECT entry_id, attribute_id, entry_key, annotation_kind,
                   method_name, method_version, CAST(conditions_json AS VARCHAR),
                   source_id, is_mutable, description
            FROM Entries WHERE attribute_id = ? ORDER BY entry_key
            """,
            [attribute_id],
        ).fetchall()
    return [
        EntryRecord(
            entry_id=row[0],
            attribute_id=row[1],
            entry_key=row[2],
            annotation_kind=row[3],
            method_name=row[4],
            method_version=row[5],
            conditions=json.loads(row[6]),
            source_id=row[7],
            is_mutable=row[8],
            description=row[9],
        )
        for row in rows
    ]


def read_stats(settings: Settings) -> DatabaseStats:
    with connection(settings) as database_connection:
        row = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Molecules),
                   (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports),
                   (SELECT count(*) FROM Jobs)
            """
        ).fetchone()
    return DatabaseStats(
        molecules=row[0],
        attributes=row[1],
        entries=row[2],
        annotations=row[3],
        imports=row[4],
        jobs=row[5],
    )


def read_attribute_statistics(
    settings: Settings,
    attribute_id: int,
) -> list[AttributeStatistics]:
    """Compute current per-Entry statistics directly without a query cache."""
    with connection(settings) as database_connection:
        definitions = database_connection.execute(
            """
            SELECT entry_id, entry_key, attribute.value_type
            FROM Entries AS entry
            JOIN Attributes AS attribute USING (attribute_id)
            WHERE attribute.attribute_id = ?
            ORDER BY entry.entry_id
            """,
            [attribute_id],
        ).fetchall()
        if not definitions and database_connection.execute(
            "SELECT 1 FROM Attributes WHERE attribute_id = ?",
            [attribute_id],
        ).fetchone() is None:
            raise KeyError(attribute_id)

        statistics = []
        for entry_id, entry_key, value_type in definitions:
            statistics.append(
                _entry_statistics(
                    database_connection,
                    attribute_id=int(attribute_id),
                    entry_id=int(entry_id),
                    entry_key=entry_key,
                    value_type=value_type,
                )
            )
    return statistics


def _entry_statistics(
    database_connection,
    *,
    attribute_id: int,
    entry_id: int,
    entry_key: str,
    value_type: str,
) -> AttributeStatistics:
    column = {
        "number": "value_number",
        "text": "value_text",
        "boolean": "value_boolean",
    }[value_type]
    if value_type == "number":
        row = database_connection.execute(
            f"""
            SELECT count({column}), count(DISTINCT {column}),
                   min({column}), max({column}), avg({column}),
                   median({column}), stddev_samp({column})
            FROM Annotations WHERE entry_id = ?
            """,
            [entry_id],
        ).fetchone()
        return AttributeStatistics(
            attribute_id=attribute_id,
            entry_id=entry_id,
            entry_key=entry_key,
            value_type=value_type,
            count=row[0],
            distinct_count=row[1],
            min=row[2],
            max=row[3],
            mean=row[4],
            median=row[5],
            std=row[6],
        )
    row = database_connection.execute(
        f"""
        SELECT count({column}), count(DISTINCT {column}),
               count(*) FILTER (WHERE value_boolean = true),
               count(*) FILTER (WHERE value_boolean = false)
        FROM Annotations WHERE entry_id = ?
        """,
        [entry_id],
    ).fetchone()
    return AttributeStatistics(
        attribute_id=attribute_id,
        entry_id=entry_id,
        entry_key=entry_key,
        value_type=value_type,
        count=row[0],
        distinct_count=row[1],
        true_count=row[2] if value_type == "boolean" else None,
        false_count=row[3] if value_type == "boolean" else None,
    )


_IMPORT_COLUMNS = (
    "import_id", "source_id", "file_name", "file_hash", "data_type", "status",
    "processor_name", "total_rows", "valid_rows", "new_rows", "existing_rows",
    "duplicate_rows", "accepted_rows", "failed_rows", "error_message", "created_at",
    "finished_at",
)
_IMPORT_SELECT = """
    SELECT import_id, source_id, file_name, file_hash, data_type, status,
           processor_name, total_rows, valid_rows, new_rows, existing_rows,
           duplicate_rows, accepted_rows, failed_rows, error_message,
           created_at, finished_at
    FROM Imports
"""
