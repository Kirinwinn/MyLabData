"""Set-based DuckDB operations for Molecules files."""

from pathlib import Path

import duckdb

from mylabdata.core.exceptions import MoleculeFileError

STAGING_TABLE = "_staged_molecules"
NEW_MOLECULES_TABLE = "_new_molecules"
NUMBERED_MOLECULES_TABLE = "_numbered_molecules"


def validate_molecule_parquet_schema(
    database_connection: duckdb.DuckDBPyConnection,
    file_path: Path,
) -> None:
    """Require one VARCHAR canonical_smiles column; ignore additional columns."""
    try:
        relation = database_connection.read_parquet(str(file_path))
        columns = dict(zip(relation.columns, map(str, relation.types), strict=True))
    except (duckdb.Error, OSError) as exc:
        raise MoleculeFileError(f"Unable to read Molecules Parquet file: {exc}") from exc

    if "canonical_smiles" not in columns:
        raise MoleculeFileError("Missing required column: canonical_smiles")
    if columns["canonical_smiles"].upper() != "VARCHAR":
        raise MoleculeFileError(
            "canonical_smiles must be VARCHAR, "
            f"received {columns['canonical_smiles']}"
        )


def stage_molecule_file(
    database_connection: duckdb.DuckDBPyConnection,
    file_path: Path,
) -> None:
    """Materialize normalized input rows in a connection-local temp table."""
    validate_molecule_parquet_schema(database_connection, file_path)
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {STAGING_TABLE} AS
        SELECT
            row_number() OVER () AS source_row_number,
            trim(canonical_smiles) AS canonical_smiles
        FROM read_parquet(?)
        """,
        [str(file_path)],
    )


def molecule_preview_counts(
    database_connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    """Calculate all preview counts with set-based SQL."""
    row = database_connection.execute(
        f"""
        WITH valid AS (
            SELECT canonical_smiles
            FROM {STAGING_TABLE}
            WHERE canonical_smiles IS NOT NULL
              AND length(canonical_smiles) > 0
        ),
        distinct_valid AS (
            SELECT DISTINCT canonical_smiles
            FROM valid
        ),
        existing AS (
            SELECT candidate.canonical_smiles
            FROM distinct_valid AS candidate
            SEMI JOIN Molecules AS molecule
              ON molecule.canonical_smiles = candidate.canonical_smiles
        )
        SELECT
            (SELECT count(*) FROM {STAGING_TABLE}) AS total_rows,
            (SELECT count(*) FROM valid) AS valid_rows,
            (SELECT count(*) FROM distinct_valid) AS distinct_valid_rows,
            (SELECT count(*) FROM existing) AS existing_rows
        """
    ).fetchone()

    total_rows, valid_rows, distinct_valid_rows, existing_rows = map(int, row)
    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "new_rows": distinct_valid_rows - existing_rows,
        "existing_rows": existing_rows,
        "duplicate_rows": valid_rows - distinct_valid_rows,
        "invalid_rows": total_rows - valid_rows,
    }


def insert_staged_molecules(
    database_connection: duckdb.DuckDBPyConnection,
) -> int:
    """Insert all distinct new molecules without Python row iteration."""
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {NEW_MOLECULES_TABLE} AS
        SELECT
            staged.canonical_smiles,
            min(staged.source_row_number) AS source_order
        FROM {STAGING_TABLE} AS staged
        ANTI JOIN Molecules AS molecule
          ON molecule.canonical_smiles = staged.canonical_smiles
        WHERE staged.canonical_smiles IS NOT NULL
          AND length(staged.canonical_smiles) > 0
        GROUP BY staged.canonical_smiles
        """
    )
    inserted_rows = int(
        database_connection.execute(
            f"SELECT count(*) FROM {NEW_MOLECULES_TABLE}"
        ).fetchone()[0]
    )

    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {NUMBERED_MOLECULES_TABLE} AS
        SELECT
            nextval('molecule_id_seq') AS molecule_id,
            canonical_smiles
        FROM {NEW_MOLECULES_TABLE}
        ORDER BY source_order
        """
    )
    database_connection.execute(
        f"""
        INSERT INTO Molecules (molecule_id, lab_id, canonical_smiles)
        SELECT
            molecule_id,
            'L' || lpad(CAST(molecule_id AS VARCHAR), 8, '0') AS lab_id,
            canonical_smiles
        FROM {NUMBERED_MOLECULES_TABLE}
        """
    )
    return inserted_rows

