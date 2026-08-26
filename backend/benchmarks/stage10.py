"""Real-scale stage-10 import and cross-query benchmark."""

import argparse
import ctypes
import json
import platform
import statistics
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.db.migrate import migrate
from mylabdata.schemas.catalog import SearchCondition, SearchRequest
from mylabdata.services.annotation_importer import import_annotation_package
from mylabdata.services.annotation_preview import preview_annotation_package
from mylabdata.services.molecule_importer import import_molecule_file
from mylabdata.services.search import search_molecules

DEFAULT_MOLECULE_ROWS = 1_000_000
DEFAULT_MEMORY_LIMIT = "512MB"
DEFAULT_QUERY_REPETITIONS = 7


def run_benchmark(
    work_directory: Path,
    *,
    molecule_rows: int = DEFAULT_MOLECULE_ROWS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    query_repetitions: int = DEFAULT_QUERY_REPETITIONS,
) -> dict[str, Any]:
    """Run actual import services and return machine-readable measurements."""
    if molecule_rows < 1:
        raise ValueError("molecule_rows must be positive")
    if query_repetitions < 1:
        raise ValueError("query_repetitions must be positive")

    data_root = work_directory / "DryData"
    settings = Settings(
        data_root=data_root,
        memory_limit=memory_limit,
        # DuckDB allocates working buffers per thread. A single thread makes
        # this benchmark exercise the configured low-memory limit itself,
        # rather than exhausting it through parallel buffer multiplication.
        threads=1,
    )
    migrate(settings)

    molecule_file = _write_molecules(settings, molecule_rows)
    started = perf_counter()
    molecule_result = import_molecule_file(molecule_file, settings)
    molecule_seconds = perf_counter() - started

    package = _write_annotations(settings, molecule_rows)
    preview_started = perf_counter()
    preview = preview_annotation_package(package, settings)
    preview_seconds = perf_counter() - preview_started
    if not preview.can_import:
        raise RuntimeError(f"generated benchmark package is invalid: {preview.errors}")
    started = perf_counter()
    annotation_result = import_annotation_package(
        package,
        preview.preview_token,
        settings,
    )
    annotation_seconds = perf_counter() - started

    request = SearchRequest(
        conditions=[
            SearchCondition(
                attribute_key="benchmark_score",
                entry_key="benchmark_score.generated",
                operator="between",
                value=200,
                second_value=300,
            ),
            SearchCondition(
                attribute_key="benchmark_active",
                entry_key="benchmark_active.generated",
                operator="eq",
                value=True,
            ),
        ],
        logic="and",
        limit=1000,
    )
    query_ms = []
    search_result = None
    for _ in range(query_repetitions):
        started = perf_counter()
        search_result = search_molecules(request, settings)
        query_ms.append((perf_counter() - started) * 1000)
    assert search_result is not None
    _assert_search_rows(search_result.molecules)

    with connection(settings, read_only=True) as database_connection:
        stored_molecules, stored_annotations, stored_imports = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Molecules),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()

    annotation_rows = molecule_rows * 2
    sorted_query_ms = sorted(query_ms)
    percentile_index = max(0, int(len(sorted_query_ms) * 0.95 + 0.9999) - 1)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "duckdb_version": duckdb.__version__,
        "configuration": {
            "memory_limit": memory_limit,
            "threads": settings.threads,
            "molecule_rows": molecule_rows,
            "annotation_rows": annotation_rows,
            "query_repetitions": query_repetitions,
        },
        "molecule_import": {
            "seconds": molecule_seconds,
            "rows_per_second": molecule_result.inserted_rows / molecule_seconds,
            "inserted_rows": molecule_result.inserted_rows,
        },
        "annotation_preview": {
            "seconds": preview_seconds,
            "expected_inserts": preview.expected_inserts,
        },
        "annotation_import": {
            "seconds": annotation_seconds,
            "rows_per_second": annotation_result.inserted_annotations
            / annotation_seconds,
            "inserted_rows": annotation_result.inserted_annotations,
        },
        "cross_query": {
            "samples_ms": query_ms,
            "median_ms": statistics.median(query_ms),
            "p95_ms": sorted_query_ms[percentile_index],
            "returned_rows": len(search_result.molecules),
        },
        "resources": {
            "database_bytes": settings.resolved_database_path.stat().st_size,
            "peak_process_rss_bytes": _peak_process_rss_bytes(),
            "temp_spill_bytes": _directory_size(settings.resolved_temp_directory),
        },
        "database_counts": {
            "molecules": int(stored_molecules),
            "annotations": int(stored_annotations),
            "imports": int(stored_imports),
        },
    }


def _write_molecules(settings: Settings, rows: int) -> Path:
    directory = settings.incoming_molecules_directory
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "benchmark_molecules.parquet"
    with duckdb.connect() as generator:
        generator.sql(
            f"""
            SELECT 'C' || CAST(i AS VARCHAR) AS canonical_smiles
            FROM range({rows}) AS generated(i)
            """
        ).write_parquet(str(destination), compression="zstd", row_group_size=100_000)
    return destination


def _write_annotations(settings: Settings, rows: int) -> Path:
    package = settings.incoming_annotations_directory / "benchmark-annotations"
    package.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "Stage10Benchmark",
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
                "method_name": "Stage10Benchmark",
            },
            {
                "entry_key": "benchmark_active.generated",
                "attribute_key": "benchmark_active",
                "annotation_kind": "calculation",
                "method_name": "Stage10Benchmark",
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
    (package / "annotation_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (package / "processing_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with duckdb.connect() as generator:
        generator.sql(
            f"""
            SELECT 'C' || CAST(i AS VARCHAR) AS canonical_smiles,
                   'benchmark_score'::VARCHAR AS attribute_key,
                   'benchmark_score.generated'::VARCHAR AS entry_key,
                   CAST(i % 1000 AS DOUBLE) AS value_number,
                   NULL::VARCHAR AS value_text,
                   NULL::BOOLEAN AS value_boolean
            FROM range({rows}) AS generated(i)
            UNION ALL
            SELECT 'C' || CAST(i AS VARCHAR),
                   'benchmark_active'::VARCHAR,
                   'benchmark_active.generated'::VARCHAR,
                   NULL::DOUBLE,
                   NULL::VARCHAR,
                   (i % 2 = 0)::BOOLEAN
            FROM range({rows}) AS generated(i)
            """
        ).write_parquet(
            str(package / "annotations.parquet"),
            compression="zstd",
            row_group_size=100_000,
        )
    return package


def _assert_search_rows(molecules: list[Any]) -> None:
    if not molecules:
        raise AssertionError("cross-query returned no rows")
    for molecule in molecules:
        value = int(molecule.canonical_smiles.removeprefix("C"))
        if not (200 <= value % 1000 <= 300 and value % 2 == 0):
            raise AssertionError(f"cross-query returned invalid row: {molecule}")


def _peak_process_rss_bytes() -> int:
    if sys.platform == "win32":
        from ctypes import wintypes

        size_t = ctypes.c_size_t

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_fault_count", wintypes.DWORD),
                ("peak_working_set_size", size_t),
                ("working_set_size", size_t),
                ("quota_peak_paged_pool_usage", size_t),
                ("quota_paged_pool_usage", size_t),
                ("quota_peak_non_paged_pool_usage", size_t),
                ("quota_non_paged_pool_usage", size_t),
                ("pagefile_usage", size_t),
                ("peak_pagefile_usage", size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        success = psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.peak_working_set_size) if success else 0
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(peak if sys.platform == "darwin" else peak * 1024)
    except (ImportError, OSError):
        return 0


def _directory_size(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_MOLECULE_ROWS)
    parser.add_argument("--memory-limit", default=DEFAULT_MEMORY_LIMIT)
    parser.add_argument("--query-repetitions", type=int, default=DEFAULT_QUERY_REPETITIONS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("stage10-benchmark.json"),
    )
    parser.add_argument("--work-directory", type=Path)
    arguments = parser.parse_args()

    if arguments.work_directory is None:
        with tempfile.TemporaryDirectory(prefix="mylabdata-stage10-") as temporary:
            result = run_benchmark(
                Path(temporary),
                molecule_rows=arguments.rows,
                memory_limit=arguments.memory_limit,
                query_repetitions=arguments.query_repetitions,
            )
    else:
        result = run_benchmark(
            arguments.work_directory,
            molecule_rows=arguments.rows,
            memory_limit=arguments.memory_limit,
            query_repetitions=arguments.query_repetitions,
        )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
