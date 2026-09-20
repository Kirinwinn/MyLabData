"""Rebuildable JSON cache records stored beneath DryData/Cache."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from access.paths import DryDataPaths


@dataclass(frozen=True, slots=True)
class CacheKey:
    """A stable cache identity tied to an explicit data revision."""

    namespace: str
    payload: str
    data_revision: str

    @property
    def filename(self) -> str:
        digest = sha256(
            f"{self.namespace}\0{self.payload}\0{self.data_revision}".encode()
        ).hexdigest()
        return f"{self.namespace}-{digest}.json"


class CacheStore:
    """Store only disposable, versioned derived data outside the core database."""

    def __init__(self, paths: DryDataPaths) -> None:
        self.paths = paths

    def read(self, key: CacheKey) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, key: CacheKey, value: dict[str, Any]) -> Path:
        """Atomically replace one derived cache record."""
        directory = self.paths.cache_directory
        directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def invalidate_namespace(self, namespace: str) -> int:
        """Delete cached records in one validated namespace and return their count."""
        if not namespace.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Cache namespace must be alphanumeric, hyphen, or underscore")
        directory = self.paths.cache_directory
        if not directory.is_dir():
            return 0
        removed = 0
        for path in directory.glob(f"{namespace}-*.json"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
                removed += 1
        return removed

    def _path(self, key: CacheKey) -> Path:
        return self.paths.cache_directory / key.filename
