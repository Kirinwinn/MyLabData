"""Real-scale benchmark for the v3 access layer and Job queues."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

import duckdb

from access.paths import DryDataPaths
from core.config import Settings
from jobs.handlers import register_builtin_handlers
from jobs.manager import JobManager

DEFAULT_ROWS = 1_000_000
DEFAULT_REPETITIONS = 7


def run_benchmark(
    work_directory: Path,
    *,
    molecule_rows: int = DEFAULT_ROWS,
    query_repetitions: int = DEFAULT_REPETITIONS,
) -> dict[str, Any]:
    """Benchmark v3 Command Jobs and Query Jobs using only temporary data."""
    if molecule_rows < 1 or query_repetitions < 1:
        raise ValueError("rows and query repetitions must be positive")
    root = work_directory / "DryData"
    _create_v3_database(root)
    settings = Settings(
        data_root=root,
        memory_limit="512MB",
        threads=1,
        query_workers=2,
    )
    _write_molecule_package(root, molecule_rows)
    manager = JobManager(settings)
    register_builtin_handlers(manager)
    manager.start()
    try:
        molecule_job = _submit_package_import(manager, root, "molecules")
        molecule_seconds = _wait(manager, molecule_job.job_id)[1]
        molecule_result = manager.get(molecule_job.job_id)
        _write_annotation_package(root, molecule_rows)
        annotation_job = _submit_package_import(manager, root, "annotations")
        annotation_seconds = _wait(manager, annotation_job.job_id)[1]
        annotation_result = manager.get(annotation_job.job_id)
        if molecule_result.status != "completed" or annotation_result.status != "completed":
            message = molecule_result.error_message or annotation_result.error_message
            raise RuntimeError(f"Command Job failed: {message}")

        query_samples = []
        for _ in range(query_repetitions):
            started = perf_counter()
            job = manager.submit("molecules_query", {"limit": 1000, "offset": 0})
            record, _ = _wait(manager, job.job_id)
            if record.status != "completed":
                raise RuntimeError(record.error_message)
            query_samples.append((perf_counter() - started) * 1000)

        concurrent_started = perf_counter()
        first = manager.submit("molecules_query", {"limit": 1000, "offset": 0})
        second = manager.submit("molecules_query", {"limit": 1000, "offset": 1000})
        first_record, _ = _wait(manager, first.job_id)
        second_record, _ = _wait(manager, second.job_id)
        concurrent_ms = (perf_counter() - concurrent_started) * 1000
        if first_record.status != "completed" or second_record.status != "completed":
            raise RuntimeError("Parallel Query Job failed")
    finally:
        manager.stop()

    sorted_samples = sorted(query_samples)
    p95_index = max(0, int(len(sorted_samples) * 0.95 + 0.9999) - 1)
    database = root / "DryData.duckdb"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "molecule_rows": molecule_rows,
            "annotation_rows": molecule_rows * 2,
            "query_repetitions": query_repetitions,
            "query_workers": settings.query_workers,
            "command_workers": 1,
        },
        "molecule_command_job": {
            "seconds": molecule_seconds,
            "rows_per_second": molecule_result.result["inserted_rows"] / molecule_seconds,
            "inserted_rows": molecule_result.result["inserted_rows"],
        },
        "annotation_command_job": {
            "seconds": annotation_seconds,
            "rows_per_second": annotation_result.result["inserted_rows"] / annotation_seconds,
            "inserted_rows": annotation_result.result["inserted_rows"],
        },
        "query_job": {
            "samples_ms": query_samples,
            "median_ms": statistics.median(query_samples),
            "p95_ms": sorted_samples[p95_index],
            "returned_rows": 1000,
        },
        "parallel_query_jobs": {"two_jobs_total_ms": concurrent_ms},
        "resources": {"database_bytes": database.stat().st_size},
    }


def _submit_package_import(manager: JobManager, root: Path, kind: str):
    paths = DryDataPaths(root)
    from access.packages import PackageStore

    packages = PackageStore(paths)
    descriptor = next(item for item in packages.list_incoming() if item.kind == kind)
    payload: dict[str, Any] = {"package_id": descriptor.package_id}
    if kind == "annotations":
        payload["preview_token"] = (
            f"annotation-preview-v1:{descriptor.name}:{packages.fingerprint(descriptor.package_id)}"
        )
    return manager.submit("package_import", payload)


def _wait(manager: JobManager, job_id: str, *, timeout: float = 180) -> tuple[Any, float]:
    started = perf_counter()
    while perf_counter() - started < timeout:
        record = manager.get(job_id)
        if record.status in {"completed", "failed", "cancelled", "archive_pending"}:
            return record, perf_counter() - started
        sleep(0.02)
    raise TimeoutError(f"Job timed out: {job_id}")


def _create_v3_database(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    database = duckdb.connect(str(root / "DryData.duckdb"))
    try:
        database.execute(
            """
            CREATE TABLE Molecules (
                molecule_id BIGINT, lab_id VARCHAR, canonical_smiles VARCHAR,
                channel VARCHAR, created_at TIMESTAMP
            );
            CREATE TABLE Attributes (
                attribute_id BIGINT, attribute_key VARCHAR, attribute_name VARCHAR,
                value_type VARCHAR, unit VARCHAR, description VARCHAR
            );
            CREATE TABLE Entries (
                entry_id BIGINT, attribute_id BIGINT, entry_key VARCHAR,
                annotation_kind VARCHAR, method_name VARCHAR, method_version VARCHAR,
                conditions_json JSON, is_mutable BOOLEAN, description VARCHAR
            );
            CREATE TABLE Annotations (
                molecule_id BIGINT, entry_id BIGINT, value_number DOUBLE,
                value_text VARCHAR, value_boolean BOOLEAN, created_at TIMESTAMP,
                updated_at TIMESTAMP
            );
            CREATE TABLE Sources (
                source_id BIGINT, source_key VARCHAR, source_type VARCHAR, description VARCHAR
            );
            CREATE TABLE Imports (
                import_id BIGINT, source_id BIGINT, file_hash VARCHAR, data_type VARCHAR,
                status VARCHAR, processor VARCHAR, total_rows BIGINT, error_message VARCHAR,
                created_at TIMESTAMP, finished_at TIMESTAMP
            );
            """
        )
    finally:
        database.close()


def _write_molecule_package(root: Path, rows: int) -> None:
    destination = root / "Incoming" / "Molecules" / "benchmark_molecules.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as generator:
        generator.sql(
            f"""
            SELECT 'C' || CAST(i AS VARCHAR) AS canonical_smiles
            FROM range({rows}) AS generated(i)
            """
        ).write_parquet(str(destination), compression="zstd", row_group_size=100_000)


def _write_annotation_package(root: Path, rows: int) -> None:
    package = root / "Incoming" / "Annotations" / "benchmark-annotations"
    package.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "V3JobBenchmark",
        "processor_version": "1.0",
        "attributes": [
            {
                "attribute_key": "benchmark_score",
                "attribute_name": "Benchmark Score",
                "value_type": "number",
            },
            {
                "attribute_key": "benchmark_active",
                "attribute_name": "Benchmark Active",
                "value_type": "boolean",
            },
        ],
        "entries": [
            {
                "entry_key": "benchmark_score.generated",
                "attribute_key": "benchmark_score",
                "annotation_kind": "calculation",
                "method_name": "V3JobBenchmark",
            },
            {
                "entry_key": "benchmark_active.generated",
                "attribute_key": "benchmark_active",
                "annotation_kind": "calculation",
                "method_name": "V3JobBenchmark",
            },
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report = {
        "status": "completed",
        "input_rows": rows,
        "output_annotations": rows * 2,
        "rejected_rows": 0,
        "duplicate_rows": 0,
        "warnings": [],
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    (package / "annotation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "processing_report.json").write_text(json.dumps(report), encoding="utf-8")
    with duckdb.connect() as generator:
        generator.sql(
            f"""
            SELECT
                'C' || CAST(i AS VARCHAR) AS canonical_smiles,
                'benchmark_score'::VARCHAR AS attribute_key,
                'benchmark_score.generated'::VARCHAR AS entry_key,
                CAST(i % 1000 AS DOUBLE) AS value_number,
                NULL::VARCHAR AS value_text,
                NULL::BOOLEAN AS value_boolean
            FROM range({rows}) AS generated(i)
            UNION ALL
            SELECT
                'C' || CAST(i AS VARCHAR),
                'benchmark_active'::VARCHAR,
                'benchmark_active.generated'::VARCHAR,
                NULL::DOUBLE,
                NULL::VARCHAR,
                (i % 2 = 0)::BOOLEAN
            FROM range({rows}) AS generated(i)
            """
        ).write_parquet(
            str(package / "annotations.parquet"), compression="zstd", row_group_size=100_000
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--query-repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--output", type=Path, default=Path("jobs-v3-benchmark.json"))
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mylabdata-v3-jobs-") as temporary:
        metrics = run_benchmark(
            Path(temporary),
            molecule_rows=arguments.rows,
            query_repetitions=arguments.query_repetitions,
        )
    arguments.output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
