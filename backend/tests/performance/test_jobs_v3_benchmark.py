"""Opt-in real-scale benchmark assertions."""

import os
from pathlib import Path

from benchmarks.jobs_v3 import run_benchmark


def test_low_memory_large_import_and_cross_query(tmp_path: Path) -> None:
    rows = int(os.getenv("MLD_BENCH_MOLECULE_ROWS", "1000000"))
    query_repetitions = int(os.getenv("MLD_BENCH_QUERY_REPETITIONS", "7"))

    metrics = run_benchmark(
        tmp_path,
        molecule_rows=rows,
        query_repetitions=query_repetitions,
    )

    assert metrics["molecule_command_job"]["inserted_rows"] == rows
    assert metrics["annotation_command_job"]["inserted_rows"] == rows * 2
    assert metrics["molecule_command_job"]["rows_per_second"] > 0
    assert metrics["annotation_command_job"]["rows_per_second"] > 0
    assert metrics["query_job"]["returned_rows"] > 0
    assert metrics["query_job"]["p95_ms"] >= 0
    assert metrics["parallel_query_jobs"]["two_jobs_total_ms"] >= 0
    assert metrics["resources"]["database_bytes"] > 0
