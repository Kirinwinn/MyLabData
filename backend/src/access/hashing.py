"""Deterministic SHA-256 fingerprints for managed DryData files and packages."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

HASH_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash one regular file without loading it wholly into memory."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_package(path: Path) -> str:
    """Hash regular files in one package directory in deterministic name order."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"Expected a regular package directory: {path}")
    digest = sha256()
    for item in sorted(path.iterdir(), key=lambda candidate: candidate.name):
        if item.is_symlink() or not item.is_file():
            raise ValueError(f"Package entries must be regular files: {item}")
        encoded_name = item.name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(item.stat().st_size.to_bytes(8, "big"))
        with item.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_SIZE):
                digest.update(chunk)
    return digest.hexdigest()
