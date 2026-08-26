"""Integration tests for stage-7 search, statistics, and Property mutation."""

from pathlib import Path

import pytest

from mylabdata.core.config import Settings
from mylabdata.core.exceptions import ConflictError, ValidationError
from mylabdata.db.connection import connection
from mylabdata.db.migrate import migrate
from mylabdata.schemas.catalog import (
    PropertyUpdateRequest,
    SearchCondition,
    SearchRequest,
)
from mylabdata.services.catalog_reader import (
    find_molecule_by_lab_id,
    find_molecule_by_smiles,
    read_attribute_statistics,
)
from mylabdata.services.property_editor import update_property
from mylabdata.services.search import search_molecules


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)


def seed_catalog(settings: Settings) -> dict[str, int]:
    migrate(settings)
    with connection(settings) as database_connection:
        database_connection.execute(
            """
            INSERT INTO Molecules (lab_id, canonical_smiles) VALUES
                ('L00000001', 'CCO'),
                ('L00000002', 'CCN'),
                ('L00000003', 'CCC')
            """
        )
        database_connection.execute(
            """
            INSERT INTO Attributes (attribute_key, attribute_name, value_type) VALUES
                ('score', 'Score', 'number'),
                ('label', 'Label', 'text'),
                ('active', 'Active', 'boolean'),
                ('purchased', 'Purchased', 'boolean')
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries (
                attribute_id, entry_key, annotation_kind, method_name, is_mutable
            )
            SELECT attribute_id, attribute_key || '.default',
                   CASE WHEN attribute_key = 'purchased'
                        THEN 'property' ELSE 'calculation' END,
                   'Test', attribute_key = 'purchased'
            FROM Attributes
            """
        )
        identifiers = {
            row[0]: (row[1], row[2])
            for row in database_connection.execute(
                """
                SELECT attribute.attribute_key, attribute.attribute_id, entry.entry_id
                FROM Attributes AS attribute JOIN Entries AS entry USING (attribute_id)
                """
            ).fetchall()
        }
        molecules = {
            row[0]: row[1]
            for row in database_connection.execute(
                "SELECT canonical_smiles, molecule_id FROM Molecules"
            ).fetchall()
        }
        for smiles, score, label, active in (
            ("CCO", 550.0, "alpha", True),
            ("CCN", 650.0, "beta", True),
            ("CCC", 520.0, "alphabet", False),
        ):
            molecule_id = molecules[smiles]
            database_connection.execute(
                "INSERT INTO Annotations (molecule_id, entry_id, value_number) VALUES (?, ?, ?)",
                [molecule_id, identifiers["score"][1], score],
            )
            database_connection.execute(
                "INSERT INTO Annotations (molecule_id, entry_id, value_text) VALUES (?, ?, ?)",
                [molecule_id, identifiers["label"][1], label],
            )
            database_connection.execute(
                "INSERT INTO Annotations (molecule_id, entry_id, value_boolean) VALUES (?, ?, ?)",
                [molecule_id, identifiers["active"][1], active],
            )
    return {
        f"{key}_attribute": value[0] for key, value in identifiers.items()
    } | {f"{key}_entry": value[1] for key, value in identifiers.items()}


def condition(ids: dict[str, int], key: str, operator: str, value, second=None):
    return SearchCondition(
        attribute_id=ids[f"{key}_attribute"],
        entry_id=ids[f"{key}_entry"],
        operator=operator,
        value=value,
        second_value=second,
    )


def test_multiple_entry_conditions_support_and_and_or(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    intersection = search_molecules(
        SearchRequest(
            conditions=[
                condition(ids, "score", "between", 500, 600),
                condition(ids, "active", "eq", True),
            ]
        ),
        settings,
    )
    union = search_molecules(
        SearchRequest(
            conditions=[
                condition(ids, "score", "gt", 600),
                condition(ids, "active", "eq", False),
            ],
            logic="or",
        ),
        settings,
    )
    text = search_molecules(
        SearchRequest(conditions=[condition(ids, "label", "contains", "alpha")]),
        settings,
    )

    assert [item.canonical_smiles for item in intersection.molecules] == ["CCO"]
    assert [item.canonical_smiles for item in union.molecules] == ["CCN", "CCC"]
    assert [item.canonical_smiles for item in text.molecules] == ["CCO", "CCC"]
    assert intersection.elapsed_ms >= 0


def test_search_rejects_type_and_catalog_mismatches(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    with pytest.raises(ValidationError, match="invalid for number"):
        search_molecules(
            SearchRequest(conditions=[condition(ids, "score", "contains", "5")]),
            settings,
        )
    mismatched = SearchCondition(
        attribute_id=ids["score_attribute"],
        entry_id=ids["active_entry"],
        operator="eq",
        value=True,
    )
    with pytest.raises(ValidationError, match="do not identify"):
        search_molecules(SearchRequest(conditions=[mismatched]), settings)


def test_mutable_property_update_records_time_source_and_old_value(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    first = update_property(
        1,
        ids["purchased_entry"],
        PropertyUpdateRequest(value_boolean=True, source="manual:user-a"),
        settings,
    )
    second = update_property(
        1,
        ids["purchased_entry"],
        PropertyUpdateRequest(value_boolean=False, source="manual:user-b"),
        settings,
    )

    assert first.created
    assert not second.created
    with connection(settings, read_only=True) as database_connection:
        value = database_connection.execute(
            "SELECT value_boolean FROM Annotations WHERE molecule_id = 1 AND entry_id = ?",
            [ids["purchased_entry"]],
        ).fetchone()
        history = database_connection.execute(
            """
            SELECT old_value_boolean, new_value_boolean, change_source, changed_at
            FROM PropertyChanges ORDER BY change_id
            """
        ).fetchall()
    assert value == (False,)
    assert [row[:3] for row in history] == [
        (None, True, "manual:user-a"),
        (True, False, "manual:user-b"),
    ]
    assert all(row[3] is not None for row in history)


def test_prediction_or_calculation_cannot_be_modified(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    with pytest.raises(ConflictError, match="Only Entries"):
        update_property(
            1,
            ids["active_entry"],
            PropertyUpdateRequest(value_boolean=False, source="manual:user"),
            settings,
        )
    with connection(settings, read_only=True) as database_connection:
        assert database_connection.execute(
            "SELECT count(*) FROM PropertyChanges"
        ).fetchone() == (0,)


def test_property_update_rejects_value_type_mismatch_without_history(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    with pytest.raises(ValidationError, match="requires 'boolean', received 'text'"):
        update_property(
            1,
            ids["purchased_entry"],
            PropertyUpdateRequest(value_text="yes", source="manual:user"),
            settings,
        )
    with connection(settings, read_only=True) as database_connection:
        assert database_connection.execute(
            "SELECT count(*) FROM PropertyChanges"
        ).fetchone() == (0,)


def test_exact_lookup_and_live_attribute_statistics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    ids = seed_catalog(settings)
    assert find_molecule_by_lab_id(settings, "L00000002").canonical_smiles == "CCN"
    assert find_molecule_by_smiles(settings, "CCC").lab_id == "L00000003"
    score = read_attribute_statistics(settings, ids["score_attribute"])[0]
    active = read_attribute_statistics(settings, ids["active_attribute"])[0]
    assert (score.count, score.min, score.max) == (3, 520.0, 650.0)
    assert (active.true_count, active.false_count) == (2, 1)
