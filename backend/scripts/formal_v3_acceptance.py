"""Run one narrowly scoped v3 acceptance import against an explicit DryData root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic, sleep

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from access.database import DryDataDatabase
from access.paths import DryDataPaths
from core.config import Settings
from jobs.handlers import register_builtin_handlers
from jobs.manager import JobManager

PACKAGE_NAME = "formal-acceptance-existing-molecule-20260914.parquet"


def _counts(database_path: Path) -> tuple[int, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        return connection.execute(
            """
            SELECT (SELECT count(*) FROM Molecules),
                   (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Sources),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()


def _wait(manager: JobManager, job_id: str, timeout: float = 30):
    deadline = monotonic() + timeout
    stable = {"completed", "failed", "cancelled", "waiting_confirmation", "archive_pending"}
    while monotonic() < deadline:
        job = manager.get(job_id)
        if job.status in stable:
            return job
        sleep(0.02)
    raise TimeoutError(job_id)


def run(root: Path) -> dict:
    paths = DryDataPaths(root)
    DryDataDatabase(paths).verify_v3_schema()
    incoming = paths.package_directory("incoming", "molecules") / PACKAGE_NAME
    processed = paths.package_directory("processed", "molecules") / PACKAGE_NAME
    if incoming.exists() or processed.exists():
        raise FileExistsError(f"Acceptance package already exists: {PACKAGE_NAME}")

    before = _counts(paths.database_path)
    with duckdb.connect(str(paths.database_path), read_only=True) as connection:
        molecule_id, canonical_smiles = connection.execute(
            """
            SELECT molecule_id, canonical_smiles
            FROM Molecules ORDER BY molecule_id LIMIT 1
            """
        ).fetchone()
    pq.write_table(
        pa.table({"canonical_smiles": pa.array([canonical_smiles], pa.string())}),
        incoming,
    )

    settings = Settings(data_root=paths.root, memory_limit="1GB", threads=1)
    manager = JobManager(settings)
    register_builtin_handlers(manager)
    manager.start()
    try:
        package_query = _wait(manager, manager.submit("packages_query", {}).job_id)
        package = next(
            item for item in package_query.result["items"] if item["package_name"] == PACKAGE_NAME
        )
        preview = _wait(
            manager,
            manager.submit("package_preview", {"package_id": package["package_id"]}).job_id,
        )
        imported = _wait(
            manager,
            manager.submit("package_import", {"package_id": package["package_id"]}).job_id,
        )
    finally:
        manager.stop(wait=True)

    after = _counts(paths.database_path)
    expected = (*before[:5], before[5] + 1)
    if package_query.status != "completed":
        raise RuntimeError(package_query.error_message)
    if preview.status != "completed" or preview.result["existing_rows"] != 1:
        raise RuntimeError(preview.error_message or "Unexpected preview result")
    if imported.status != "completed" or imported.result["inserted_rows"] != 0:
        raise RuntimeError(imported.error_message or "Unexpected import result")
    if after != expected:
        raise RuntimeError(f"Unexpected business counts: before={before}, after={after}")
    if incoming.exists() or not processed.is_file():
        raise RuntimeError("Acceptance package was not archived correctly")
    return {
        "source_molecule_id": int(molecule_id),
        "package_name": PACKAGE_NAME,
        "preview": preview.result,
        "import": imported.result,
        "counts_before": before,
        "counts_after": after,
        "processed_path": str(processed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.root), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
