"""Integration tests for registered catalog definition lookups."""

from __future__ import annotations

from pathlib import Path

import duckdb

from access.catalog import CatalogRepository
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
            """
            INSERT INTO Attributes VALUES
              (1, 'absorption_wavelength', 'Absorption Wavelength', 'number', 'nm',
               '分子紫外最强吸收波长')
            """
        )
        database.execute(
            """
            INSERT INTO Entries VALUES
              (1, 1, 'absorption_wavelength.deepmpp.CS(C)=O', 'prediction', 'DeepMPP',
               NULL, '{"solvent_smiles": "CS(C)=O"}', FALSE,
               'DeepMPP 在 CS(C)=O 条件下预测的 Absorption Wavelength。')
            """
        )


def test_attribute_and_entry_lookups_return_registered_definitions(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    repository = CatalogRepository(DryDataDatabase(DryDataPaths(root)))

    attribute = repository.attribute_by_key("absorption_wavelength")
    assert attribute is not None
    assert attribute.attribute_name == "Absorption Wavelength"
    assert (attribute.value_type, attribute.unit) == ("number", "nm")
    assert attribute.description == "分子紫外最强吸收波长"
    assert repository.attribute_by_key("missing_attribute") is None

    entry = repository.entry_by_key("absorption_wavelength.deepmpp.CS(C)=O")
    assert entry is not None
    assert entry.attribute_key == "absorption_wavelength"
    assert entry.annotation_kind == "prediction"
    assert entry.method_name == "DeepMPP"
    assert entry.method_version is None
    assert entry.conditions == {"solvent_smiles": "CS(C)=O"}
    assert entry.is_mutable is False
    assert entry.description == "DeepMPP 在 CS(C)=O 条件下预测的 Absorption Wavelength。"
    assert repository.entry_by_key("missing.entry") is None
