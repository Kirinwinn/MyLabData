"""Managed Molecules files and Annotation Packages beneath the DryData root."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from access.hashing import sha256_file, sha256_package
from access.paths import DryDataPathError, DryDataPaths, PackageKind, PackageState


@dataclass(frozen=True, slots=True)
class PackageDescriptor:
    """A path-free description safe for use by services and API responses."""

    package_id: str
    kind: PackageKind
    name: str
    size_bytes: int
    modified_at: datetime
    files: tuple[str, ...]


class PackageStore:
    """Scan, read, fingerprint, and archive trusted incoming packages."""

    def __init__(self, paths: DryDataPaths) -> None:
        self.paths = paths

    def list_incoming(self) -> list[PackageDescriptor]:
        """List supported incoming items without exposing filesystem paths."""
        descriptors = self._molecule_descriptors() + self._annotation_descriptors()
        return sorted(descriptors, key=lambda item: (item.kind, item.name.casefold()))

    def descriptor(self, package_id: str) -> PackageDescriptor:
        for descriptor in self.list_incoming():
            if descriptor.package_id == package_id:
                return descriptor
        raise KeyError(f"Unknown incoming package: {package_id}")

    def fingerprint(self, package_id: str) -> str:
        """Return the current content hash for one incoming package."""
        descriptor = self.descriptor(package_id)
        path = self._incoming_path(descriptor)
        return sha256_file(path) if descriptor.kind == "molecules" else sha256_package(path)

    def read_json(self, package_id: str, file_name: str) -> dict[str, Any]:
        """Read one JSON file from an incoming Annotation Package."""
        descriptor = self.descriptor(package_id)
        if descriptor.kind != "annotations":
            raise ValueError("Only Annotation Packages contain managed JSON files")
        if file_name not in descriptor.files:
            raise FileNotFoundError(file_name)
        path = self._incoming_path(descriptor) / file_name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {file_name}") from exc

    def archive(self, package_id: str, state: PackageState) -> PackageDescriptor:
        """Move a current incoming package to Processed or Failed without overwriting."""
        if state == "incoming":
            raise ValueError("Incoming packages cannot be archived into Incoming")
        descriptor = self.descriptor(package_id)
        source = self._incoming_path(descriptor)
        destination_directory = self.paths.package_directory(state, descriptor.kind)
        destination = destination_directory / source.name
        if destination.exists():
            raise FileExistsError(f"Archive destination already exists: {destination.name}")
        destination_directory.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return self._descriptor(descriptor.kind, destination)

    def _molecule_descriptors(self) -> list[PackageDescriptor]:
        directory = self.paths.package_directory("incoming", "molecules")
        if not directory.is_dir():
            return []
        return [
            self._descriptor("molecules", item)
            for item in directory.iterdir()
            if not item.is_symlink() and item.is_file() and item.suffix.casefold() == ".parquet"
        ]

    def _annotation_descriptors(self) -> list[PackageDescriptor]:
        directory = self.paths.package_directory("incoming", "annotations")
        if not directory.is_dir():
            return []
        return [
            self._descriptor("annotations", item)
            for item in directory.iterdir()
            if not item.is_symlink() and item.is_dir()
        ]

    def _descriptor(self, kind: PackageKind, path: Path) -> PackageDescriptor:
        safe_path = self.paths.require_within_root(path, must_exist=True)
        if kind == "molecules":
            files = (safe_path.name,)
            stat_items = (safe_path.stat(),)
        else:
            package_files = tuple(
                item for item in safe_path.iterdir() if not item.is_symlink() and item.is_file()
            )
            files = tuple(sorted(item.name for item in package_files))
            stat_items = tuple(item.stat() for item in package_files)
        if not stat_items:
            raise DryDataPathError(f"Package has no regular files: {safe_path.name}")
        return PackageDescriptor(
            package_id=_package_id(kind, safe_path.name),
            kind=kind,
            name=safe_path.name,
            size_bytes=sum(item.st_size for item in stat_items),
            modified_at=datetime.fromtimestamp(max(item.st_mtime for item in stat_items), tz=UTC),
            files=files,
        )

    def _incoming_path(self, descriptor: PackageDescriptor) -> Path:
        path = self.paths.package_directory("incoming", descriptor.kind) / descriptor.name
        return self.paths.require_within_root(path, must_exist=True)


def _package_id(kind: PackageKind, name: str) -> str:
    """Return a stable opaque identifier, never a user-supplied file path."""
    prefix = "mol" if kind == "molecules" else "ann"
    digest = sha256(f"{kind}\0{name}".encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"
