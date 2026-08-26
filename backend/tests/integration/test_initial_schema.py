"""Integration tests for the initial MyLabData business schema."""

from pathlib import Path

import duckdb
import pytest

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.db.migrate import get_schema_version, migrate

EXPECTED_TABLES = {
    "Annotations",
    "AttributeDistributions",
    "AttributeStats",
    "Attributes",
    "Entries",
    "Imports",
    "Jobs",
    "Molecules",
    "PropertyChanges",
    "Sources",
    "_schema_migrations",
}

EXPECTED_COLUMNS = {
    "Annotations": {
        "molecule_id",
        "entry_id",
        "value_number",
        "value_text",
        "value_boolean",
        "created_at",
        "updated_at",
    },
    "AttributeDistributions": {
        "attribute_id",
        "scope_definition",
        "distribution_data",
        "data_revision",
        "updated_at",
    },
    "AttributeStats": {
        "attribute_id",
        "entry_id",
        "count",
        "null_count",
        "min",
        "max",
        "mean",
        "median",
        "std",
        "updated_at",
    },
    "Attributes": {
        "attribute_id",
        "attribute_key",
        "attribute_name",
        "value_type",
        "unit",
        "description",
    },
    "Entries": {
        "entry_id",
        "attribute_id",
        "entry_key",
        "annotation_kind",
        "method_name",
        "method_version",
        "conditions_json",
        "source_id",
        "is_mutable",
        "description",
    },
    "Imports": {
        "import_id",
        "source_id",
        "file_name",
        "file_hash",
        "data_type",
        "status",
        "processor_name",
        "total_rows",
        "valid_rows",
        "new_rows",
        "existing_rows",
        "duplicate_rows",
        "accepted_rows",
        "failed_rows",
        "error_message",
        "created_at",
        "finished_at",
    },
    "Molecules": {"molecule_id", "lab_id", "canonical_smiles", "created_at"},
    "Jobs": {
        "job_id",
        "job_type",
        "status",
        "progress",
        "message",
        "payload_json",
        "result_json",
        "error_message",
        "cancel_requested",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    },
    "PropertyChanges": {
        "change_id",
        "molecule_id",
        "entry_id",
        "old_value_number",
        "old_value_text",
        "old_value_boolean",
        "new_value_number",
        "new_value_text",
        "new_value_boolean",
        "change_source",
        "changed_at",
    },
    "Sources": {
        "source_id",
        "source_key",
        "source_name",
        "source_type",
        "description",
    },
}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)


def test_all_migrations_create_expected_tables(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    assert migrate(settings) == 4

    with connection(settings, read_only=True) as database_connection:
        assert get_schema_version(database_connection) == 4
        tables = {
            row[0]
            for row in database_connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchall()
        }

    assert tables == EXPECTED_TABLES


def test_initial_business_tables_have_expected_columns(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings, read_only=True) as database_connection:
        rows = database_connection.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
            """
        ).fetchall()

    actual: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        if table_name in EXPECTED_COLUMNS:
            actual.setdefault(table_name, set()).add(column_name)

    assert actual == EXPECTED_COLUMNS


def test_core_records_use_global_sequence_ids(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings) as database_connection:
        source_id = database_connection.execute(
            """
            INSERT INTO Sources (source_key, source_name, source_type)
            VALUES ('rdkit', 'RDKit', 'software')
            RETURNING source_id
            """
        ).fetchone()[0]
        attribute_id = database_connection.execute(
            """
            INSERT INTO Attributes (
                attribute_key,
                attribute_name,
                value_type,
                unit
            )
            VALUES ('molecular_weight', 'Molecular Weight', 'number', 'g/mol')
            RETURNING attribute_id
            """
        ).fetchone()[0]
        entry_id = database_connection.execute(
            """
            INSERT INTO Entries (
                attribute_id,
                entry_key,
                annotation_kind,
                method_name,
                method_version,
                source_id
            )
            VALUES (?, 'molecular_weight.rdkit', 'calculation', 'RDKit', '2025.09', ?)
            RETURNING entry_id
            """,
            [attribute_id, source_id],
        ).fetchone()[0]
        molecule_id = database_connection.execute(
            """
            INSERT INTO Molecules (lab_id, canonical_smiles)
            VALUES ('L00000001', 'CCO')
            RETURNING molecule_id
            """
        ).fetchone()[0]
        database_connection.execute(
            """
            INSERT INTO Annotations (molecule_id, entry_id, value_number)
            VALUES (?, ?, 46.07)
            """,
            [molecule_id, entry_id],
        )

        annotation = database_connection.execute(
            """
            SELECT molecule_id, entry_id, value_number
            FROM Annotations
            """
        ).fetchone()

    assert source_id == 1
    assert attribute_id == 1
    assert entry_id == 1
    assert molecule_id == 1
    assert annotation == (1, 1, 46.07)


def test_molecule_uniqueness_is_enforced(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings) as database_connection:
        database_connection.execute(
            "INSERT INTO Molecules (lab_id, canonical_smiles) VALUES ('L00000001', 'CCO')"
        )

        with pytest.raises(duckdb.ConstraintException):
            database_connection.execute(
                "INSERT INTO Molecules (lab_id, canonical_smiles) "
                "VALUES ('L00000002', 'CCO')"
            )


@pytest.mark.parametrize(
    ("columns", "values"),
    [
        ("value_number, value_text", "1.0, 'invalid'"),
        ("value_number, value_text, value_boolean", "NULL, NULL, NULL"),
    ],
)
def test_annotation_requires_exactly_one_value(
    tmp_path: Path,
    columns: str,
    values: str,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings) as database_connection:
        database_connection.execute(
            "INSERT INTO Molecules (lab_id, canonical_smiles) VALUES ('L00000001', 'CCO')"
        )
        database_connection.execute(
            """
            INSERT INTO Attributes (attribute_key, attribute_name, value_type)
            VALUES ('test_value', 'Test Value', 'number')
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries (
                attribute_id,
                entry_key,
                annotation_kind,
                method_name
            )
            VALUES (1, 'test_value.manual', 'property', 'Manual')
            """
        )

        with pytest.raises(duckdb.ConstraintException):
            database_connection.execute(
                f"""
                INSERT INTO Annotations (molecule_id, entry_id, {columns})
                VALUES (1, 1, {values})
                """
            )


def test_prediction_and_calculation_entries_cannot_be_mutable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings) as database_connection:
        database_connection.execute(
            """
            INSERT INTO Attributes (attribute_key, attribute_name, value_type)
            VALUES ('prediction_value', 'Prediction Value', 'number')
            """
        )

        with pytest.raises(duckdb.ConstraintException):
            database_connection.execute(
                """
                INSERT INTO Entries (
                    attribute_id,
                    entry_key,
                    annotation_kind,
                    method_name,
                    is_mutable
                )
                VALUES (1, 'prediction_value.model', 'prediction', 'Model', true)
                """
            )


def test_foreign_keys_reject_unknown_molecule_and_entry(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)

    with connection(settings) as database_connection:
        with pytest.raises(duckdb.ConstraintException):
            database_connection.execute(
                """
                INSERT INTO Annotations (molecule_id, entry_id, value_number)
                VALUES (999, 999, 1.0)
                """
            )
