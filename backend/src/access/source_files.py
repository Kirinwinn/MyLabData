"""Managed source data files beneath DryData/New used to build Annotation Packages."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from access.paths import DryDataPathError, DryDataPaths

_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")
_DELIMITERS = (",", ";", "\t", "|")
_INVALID_NAME_CHARACTERS = set('<>:"/\\|?*')
_BOOLEAN_VALUES = {"true", "false", "yes", "no"}


@dataclass(frozen=True, slots=True)
class SourceFileDescriptor:
    """A path-free description of one uploaded source data file."""

    name: str
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    """One source column with its inferred value type and fill counts."""

    index: int
    name: str
    value_type: str
    filled_rows: int
    empty_rows: int


@dataclass(frozen=True, slots=True)
class SourceFileProfile:
    """The parsed shape of one source data file, safe for API responses."""

    name: str
    encoding: str
    delimiter: str
    columns: tuple[ColumnProfile, ...]
    total_rows: int
    preview_rows: tuple[tuple[str, ...], ...]


class SourceFileStore:
    """Store, list, delete, and profile uploaded source data files."""

    def __init__(self, paths: DryDataPaths) -> None:
        self.paths = paths

    def list_files(self) -> list[SourceFileDescriptor]:
        """List uploaded source files without exposing filesystem paths."""
        directory = self.paths.new_directory
        if not directory.is_dir():
            return []
        return sorted(
            (
                self._descriptor(item)
                for item in directory.iterdir()
                if not item.is_symlink() and item.is_file()
            ),
            key=lambda descriptor: descriptor.name.casefold(),
        )

    def descriptor(self, name: str) -> SourceFileDescriptor:
        path = self.path(name)
        if not path.is_file():
            raise KeyError(name)
        return self._descriptor(path)

    def store(self, name: str, content: bytes, *, overwrite: bool = False) -> SourceFileDescriptor:
        """Write one uploaded file into New/ after validating its name."""
        path = self.path(name)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Source file already exists: {path.name}")
        directory = self.paths.new_directory
        directory.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f"{path.name}.tmp"
        temporary.write_bytes(content)
        temporary.replace(path)
        return self._descriptor(path)

    def delete(self, name: str) -> None:
        path = self.path(name)
        if not path.is_file():
            raise KeyError(name)
        path.unlink()

    def profile(self, name: str, *, preview_limit: int = 5) -> SourceFileProfile:
        """Parse one source file and describe its columns without touching DryData."""
        encoding, delimiter, header, data_rows = self._parse(name)
        columns = tuple(
            _column_profile(index, column_name, data_rows)
            for index, column_name in enumerate(header)
        )
        return SourceFileProfile(
            name=_safe_name(name),
            encoding=encoding,
            delimiter=delimiter,
            columns=columns,
            total_rows=len(data_rows),
            preview_rows=tuple(tuple(row) for row in data_rows[:preview_limit]),
        )

    def read_rows(self, name: str) -> tuple[list[str], list[list[str]]]:
        """Return the header and every normalized data row of one source file."""
        _encoding, _delimiter, header, data_rows = self._parse(name)
        return header, data_rows

    def path(self, name: str) -> Path:
        """Return the validated on-disk location of one source file."""
        return self.paths.require_within_root(self.paths.new_directory / _safe_name(name))

    def _parse(self, name: str) -> tuple[str, str, list[str], list[list[str]]]:
        path = self.path(name)
        if not path.is_file():
            raise KeyError(name)
        encoding, text = _decode(path.read_bytes())
        delimiter = _sniff_delimiter(text)
        rows = _read_rows(text, delimiter)
        if not rows:
            raise ValueError("Source file contains no rows")
        header = rows[0]
        if not any(header):
            raise ValueError("Source file header row is empty")
        return encoding, delimiter, header, [_normalize(row, len(header)) for row in rows[1:]]

    @staticmethod
    def _descriptor(path: Path) -> SourceFileDescriptor:
        stat = path.stat()
        return SourceFileDescriptor(
            name=path.name,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )


def _safe_name(name: str) -> str:
    candidate = name.strip()
    if not candidate:
        raise DryDataPathError("Source file name must not be empty")
    if candidate != Path(candidate).name or candidate in {".", ".."}:
        raise DryDataPathError(f"Source file name must be a plain file name: {name}")
    if candidate.startswith("."):
        raise DryDataPathError(f"Source file name must not start with a dot: {name}")
    if len(candidate) > 200:
        raise DryDataPathError("Source file name is too long")
    if any(
        character in _INVALID_NAME_CHARACTERS or ord(character) < 32 for character in candidate
    ):
        raise DryDataPathError(f"Source file name contains invalid characters: {name}")
    return candidate


def _decode(content: bytes) -> tuple[str, str]:
    if b"\x00" in content:
        raise ValueError("Source file is not a text file")
    for encoding in _ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding, text
    raise ValueError("Source file encoding is not supported")


def _sniff_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS))
        if dialect.delimiter in _DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    first_line = next((line for line in sample.splitlines() if line.strip()), "")
    counts = {delimiter: first_line.count(delimiter) for delimiter in _DELIMITERS}
    best = max(counts, key=lambda delimiter: (counts[delimiter], -_DELIMITERS.index(delimiter)))
    return best if counts[best] > 0 else ","


def _read_rows(text: str, delimiter: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(cell.strip() for cell in row)
    ]


def _normalize(row: list[str], width: int) -> list[str]:
    if len(row) >= width:
        return row[:width]
    return [*row, *([""] * (width - len(row)))]


def _column_profile(index: int, name: str, rows: list[list[str]]) -> ColumnProfile:
    values = [row[index] for row in rows]
    filled = [value for value in values if value]
    return ColumnProfile(
        index=index,
        name=name,
        value_type=_infer_value_type(filled),
        filled_rows=len(filled),
        empty_rows=len(values) - len(filled),
    )


def _infer_value_type(values: list[str]) -> str:
    if not values:
        return "text"
    if all(value.casefold() in _BOOLEAN_VALUES for value in values):
        return "boolean"
    if all(_is_number(value) for value in values):
        return "number"
    return "text"


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
