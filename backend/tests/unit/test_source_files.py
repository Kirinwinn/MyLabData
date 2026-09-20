"""Tests for the DryData/New source data file shelf."""

from __future__ import annotations

from pathlib import Path

import pytest

from access.paths import DryDataPathError, DryDataPaths
from access.source_files import SourceFileStore


def _store(tmp_path: Path) -> SourceFileStore:
    return SourceFileStore(DryDataPaths(tmp_path / "DryData"))


def test_store_list_delete_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    content = b"SMILES,value\nCCO,1.5\n"

    descriptor = store.store("results.csv", content)

    assert descriptor.name == "results.csv"
    assert descriptor.size_bytes == len(content)
    assert [item.name for item in store.list_files()] == ["results.csv"]
    assert store.descriptor("results.csv").size_bytes == len(content)

    store.delete("results.csv")
    assert store.list_files() == []


def test_store_rejects_unsafe_names(tmp_path: Path) -> None:
    store = _store(tmp_path)

    for name in ("", "   ", "../escape.csv", "sub/dir.csv", ".hidden.csv", "bad:name.csv"):
        with pytest.raises(DryDataPathError):
            store.store(name, b"a,b\n1,2\n")

    assert store.list_files() == []


def test_store_refuses_silent_overwrite(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.store("results.csv", b"a,b\n1,2\n")

    with pytest.raises(FileExistsError):
        store.store("results.csv", b"a,b\n9,9\n")

    store.store("results.csv", b"a,b\n9,9\n", overwrite=True)
    assert store.profile("results.csv").preview_rows == (("9", "9"),)


def test_missing_file_raises_key_error(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(KeyError):
        store.descriptor("missing.csv")
    with pytest.raises(KeyError):
        store.profile("missing.csv")
    with pytest.raises(KeyError):
        store.delete("missing.csv")


def test_profile_infers_column_types(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.store(
        "values.csv",
        b"SMILES,Abs,Flag,Label\nCCO,311.5,true,first\nCCC,,false,second\nCCN,400,true,\n",
    )

    profile = store.profile("values.csv")

    assert profile.encoding in {"utf-8", "utf-8-sig"}
    assert profile.delimiter == ","
    assert profile.total_rows == 3
    assert [(column.index, column.name, column.value_type) for column in profile.columns] == [
        (0, "SMILES", "text"),
        (1, "Abs", "number"),
        (2, "Flag", "boolean"),
        (3, "Label", "text"),
    ]
    assert (profile.columns[1].filled_rows, profile.columns[1].empty_rows) == (2, 1)
    assert profile.preview_rows[0] == ("CCO", "311.5", "true", "first")


def test_profile_reads_gb18030_encoded_csv(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.store("中文.csv", "分子,数值\n乙醇,1.5\n".encode("gb18030"))

    profile = store.profile("中文.csv")

    assert profile.encoding == "gb18030"
    assert profile.columns[0].name == "分子"
    assert profile.columns[1].value_type == "number"
    assert profile.preview_rows == (("乙醇", "1.5"),)


@pytest.mark.parametrize(
    ("delimiter", "content"),
    [
        (";", b"SMILES;value\nCCO;1.5\n"),
        ("\t", b"SMILES\tvalue\nCCO\t1.5\n"),
    ],
)
def test_profile_detects_delimiters(tmp_path: Path, delimiter: str, content: bytes) -> None:
    store = _store(tmp_path)
    store.store("values.csv", content)

    assert store.profile("values.csv").delimiter == delimiter


def test_profile_rejects_empty_and_binary_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.store("empty.csv", b"")
    store.store("binary.bin", b"\x00\x01\x02\x03")

    with pytest.raises(ValueError):
        store.profile("empty.csv")
    with pytest.raises(ValueError):
        store.profile("binary.bin")
