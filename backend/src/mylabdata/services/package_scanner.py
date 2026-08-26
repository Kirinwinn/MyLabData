"""Filesystem scanning for incoming data files."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from mylabdata.core.config import Settings, get_settings
from mylabdata.schemas.molecules import MoleculeFileCandidate
from mylabdata.schemas.packages import PackageDetail, PackageKind, PackageSummary


def scan_molecule_files(
    settings: Settings | None = None,
) -> list[MoleculeFileCandidate]:
    """List top-level Parquet files currently available in Incoming/Molecules."""
    resolved_settings = settings or get_settings()
    directory = resolved_settings.incoming_molecules_directory
    if not directory.is_dir():
        return []

    candidates: list[MoleculeFileCandidate] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_symlink() or not path.is_file() or path.suffix.casefold() != ".parquet":
            continue
        stat = path.stat()
        candidates.append(
            MoleculeFileCandidate(
                path=path.resolve(),
                file_name=path.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )
    return candidates


def scan_packages(settings: Settings | None = None) -> list[PackageSummary]:
    """Return public descriptors for all supported incoming packages."""
    resolved = settings or get_settings()
    packages: list[PackageSummary] = []
    for candidate in scan_molecule_files(resolved):
        packages.append(
            PackageSummary(
                package_id=_package_id("molecules", candidate.file_name),
                package_kind="molecules",
                package_name=candidate.file_name,
                size_bytes=candidate.size_bytes,
                modified_at=candidate.modified_at,
            )
        )

    directory = resolved.incoming_annotations_directory
    if directory.is_dir():
        for package_path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            if package_path.is_symlink() or not package_path.is_dir():
                continue
            files = [item for item in package_path.iterdir() if item.is_file()]
            if not files:
                continue
            stats = [item.stat() for item in files]
            packages.append(
                PackageSummary(
                    package_id=_package_id("annotations", package_path.name),
                    package_kind="annotations",
                    package_name=package_path.name,
                    size_bytes=sum(item.st_size for item in stats),
                    modified_at=datetime.fromtimestamp(
                        max(item.st_mtime for item in stats),
                        tz=UTC,
                    ),
                )
            )
    return sorted(packages, key=lambda item: (item.package_kind, item.package_name.casefold()))


def get_package(
    package_id: str,
    settings: Settings | None = None,
) -> tuple[PackageDetail, Path]:
    """Resolve an opaque ID only by rescanning trusted incoming directories."""
    resolved = settings or get_settings()
    for summary in scan_packages(resolved):
        if summary.package_id != package_id:
            continue
        if summary.package_kind == "molecules":
            path = resolved.incoming_molecules_directory / summary.package_name
            files = [summary.package_name]
        else:
            path = resolved.incoming_annotations_directory / summary.package_name
            files = sorted(item.name for item in path.iterdir() if item.is_file())
        return PackageDetail(**summary.model_dump(), files=files), path.resolve()
    raise KeyError(package_id)


def _package_id(kind: PackageKind, name: str) -> str:
    digest = sha256(f"{kind}\0{name}".encode()).hexdigest()[:24]
    prefix = "mol" if kind == "molecules" else "ann"
    return f"{prefix}_{digest}"
