"""Integration tests for cached, single-pass attribute statistics."""

from __future__ import annotations

from pathlib import Path

import duckdb

from access.cache import CacheStore
from access.catalog import STATISTICS_NAMESPACE, CatalogRepository
from access.database import DryDataDatabase
from access.paths import DryDataPaths


def _create_v3_database(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            """
            CREATE TABLE Molecules (molecule_id BIGINT, lab_id VARCHAR,
              canonical_smiles VARCHAR, channel VARCHAR, created_at TIMESTAMP);
            CREATE TABLE Attributes (attribute_id BIGINT, attribute_key VARCHAR,
              attribute_name VARCHAR, value_type VARCHAR, unit VARCHAR,
              description VARCHAR);
            CREATE TABLE Entries (entry_id BIGINT, attribute_id BIGINT,
              entry_key VARCHAR, annotation_kind VARCHAR, method_name VARCHAR,
              method_version VARCHAR, conditions_json JSON, is_mutable BOOLEAN,
              description VARCHAR);
            CREATE TABLE Annotations (molecule_id BIGINT, entry_id BIGINT,
              value_number DOUBLE, value_text VARCHAR, value_boolean BOOLEAN,
              created_at TIMESTAMP, updated_at TIMESTAMP);
            CREATE TABLE Sources (source_id BIGINT, source_key VARCHAR,
              source_type VARCHAR, description VARCHAR);
            CREATE TABLE Imports (import_id BIGINT, source_id BIGINT,
              file_hash VARCHAR, data_type VARCHAR, status VARCHAR,
              processor VARCHAR, total_rows BIGINT, error_message VARCHAR,
              created_at TIMESTAMP, finished_at TIMESTAMP);
            """
        )
        database.execute(
            "INSERT INTO Attributes VALUES (1, 'absorption', 'Absorption Wavelength',"
            " 'number', 'nm', NULL)"
        )
        database.execute(
            "INSERT INTO Entries VALUES (1, 1, 'absorption.a', 'calculation', 'T', '1',"
            " '{}', FALSE, NULL), (2, 1, 'absorption.b', 'calculation', 'T', '1',"
            " '{}', FALSE, NULL), (3, 1, 'absorption.empty', 'calculation', 'T', '1',"
            " '{}', FALSE, NULL)"
        )
        database.execute(
            "INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, '2026-09-01'),"
            " (2, 'L2', 'CCC', NULL, '2026-09-02'), (3, 'L3', 'CCN', NULL, '2026-09-03')"
        )
        database.execute(
            "INSERT INTO Annotations VALUES (1, 1, 700, NULL, NULL, '2026-09-01', '2026-09-01'),"
            " (2, 1, 800, NULL, NULL, '2026-09-02', '2026-09-02'),"
            " (3, 1, 900, NULL, NULL, '2026-09-03', '2026-09-03'),"
            " (1, 2, 5, NULL, NULL, '2026-09-01', '2026-09-01')"
        )


def _repository(root: Path) -> CatalogRepository:
    paths = DryDataPaths(root)
    return CatalogRepository(DryDataDatabase(paths), CacheStore(paths))


def _update_value_in_place(root: Path, value: float) -> None:
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute("UPDATE Annotations SET value_number = ? WHERE entry_id = 2", [value])


def _insert_annotation(root: Path, molecule_id: int, value: float) -> None:
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            "INSERT INTO Annotations VALUES (?, 1, ?, NULL, NULL, '2026-09-04', '2026-09-04')",
            [molecule_id, value],
        )


def test_statistics_values_and_empty_entries(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    rows = _repository(root).attribute_statistics(1)

    assert [(row.entry_id, row.count) for row in rows] == [(1, 3), (2, 1), (3, 0)]
    first = rows[0]
    assert (first.min, first.max, first.mean, first.median) == (700, 900, 800, 800)
    assert first.std == 100
    second = rows[1]
    assert second.distinct_count == 1
    assert second.median == 5
    assert second.std is None
    empty = rows[2]
    assert (empty.count, empty.distinct_count, empty.min, empty.mean) == (0, 0, None, None)
    assert (empty.true_count, empty.false_count) == (None, None)


def test_repeated_calls_are_cached_until_data_or_namespace_changes(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    repository = _repository(root)

    first = repository.attribute_statistics(1)
    cache_files = list((root / "Cache").glob(f"{STATISTICS_NAMESPACE}-*.json"))
    assert len(cache_files) == 1

    _update_value_in_place(root, 12345)
    second = repository.attribute_statistics(1)
    assert second == first
    assert second[1].median == 5

    repository.cache.invalidate_namespace(STATISTICS_NAMESPACE)
    third = repository.attribute_statistics(1)
    assert third[1].median == 12345

    _insert_annotation(root, 2, 850)
    fourth = repository.attribute_statistics(1)
    assert fourth[0].count == 4
    assert fourth[0].min == 700
    assert fourth[0].max == 900


def test_statistics_without_cache_store_still_work(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    repository = CatalogRepository(DryDataDatabase(DryDataPaths(root)))
    rows = repository.attribute_statistics(1)
    assert [row.count for row in rows] == [3, 1, 0]
    assert not (root / "Cache").is_dir() or not list((root / "Cache").glob("*.json"))
