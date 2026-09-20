"""Trusted paths beneath one DryData root directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PackageKind = Literal["molecules", "annotations"]
PackageState = Literal["incoming", "processed", "failed"]


class DryDataPathError(ValueError):
    """Raised when a path would leave the configured DryData root."""


@dataclass(frozen=True, slots=True)
class DryDataPaths:
    """Resolve every managed DryData location from one root directory.

    Creating this object has no filesystem side effects. Directory creation is
    explicit through :meth:`ensure_runtime_directories`.
    """

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser().resolve())

    @property
    def database_path(self) -> Path:
        """Return the canonical third-version DryData database file."""
        return self.root / "DryData.duckdb"

    @property
    def jobs_database_path(self) -> Path:
        """Return the canonical Job-control database file."""
        return self.root / "Jobs.duckdb"

    @property
    def cache_directory(self) -> Path:
        return self.root / "Cache"

    @property
    def temp_directory(self) -> Path:
        return self.root / "Temp"

    @property
    def exports_directory(self) -> Path:
        """Return the directory where generated export files are written."""
        return self.temp_directory / "exports"

    @property
    def new_directory(self) -> Path:
        """Return the directory holding uploaded source data files."""
        return self.root / "New"

    def package_directory(self, state: PackageState, kind: PackageKind) -> Path:
        """Return one managed directory for a package kind and lifecycle state."""
        state_name = {
            "incoming": "Incoming",
            "processed": "Processed",
            "failed": "Failed",
        }[state]
        kind_name = {"molecules": "Molecules", "annotations": "Annotations"}[kind]
        return self.root / state_name / kind_name

    def runtime_directories(self) -> tuple[Path, ...]:
        """Return directories that may be explicitly created during bootstrap."""
        return (
            self.package_directory("incoming", "molecules"),
            self.package_directory("incoming", "annotations"),
            self.package_directory("processed", "molecules"),
            self.package_directory("processed", "annotations"),
            self.package_directory("failed", "molecules"),
            self.package_directory("failed", "annotations"),
            self.cache_directory,
            self.temp_directory,
            self.new_directory,
        )

    def ensure_runtime_directories(self) -> None:
        """Create the managed runtime directories when an application opts in."""
        for directory in self.runtime_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def require_within_root(self, path: Path, *, must_exist: bool = False) -> Path:
        """Resolve *path* and reject anything outside the DryData root."""
        try:
            resolved = path.resolve(strict=must_exist)
        except OSError as exc:
            raise DryDataPathError(f"Cannot resolve managed path: {path}") from exc
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise DryDataPathError(f"Path must be inside {self.root}: {path}") from exc
        return resolved
