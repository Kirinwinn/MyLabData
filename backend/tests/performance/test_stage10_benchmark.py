"""Opt-in real-scale benchmark assertions."""

import os
from pathlib import Path

from benchmarks.stage10 import run_benchmark


def test_low_memory_large_import_and_cross_query(tmp_path: Path) -> None:
    rows = int(os.getenv("MLD_BENCH_MOLECULE_ROWS", "1000000"))
    memory_limit = os.getenv("MLD_BENCH_MEMORY_LIMIT", "512MB")
    query_repetitions = int(os.getenv("MLD_BENCH_QUERY_REPETITIONS", "7"))

    metrics = run_benchmark(
        tmp_path,
        molecule_rows=rows,
        memory_limit=memory_limit,
        query_repetitions=query_repetitions,
    )

    assert metrics["database_counts"]["molecules"] == rows
    assert metrics["database_counts"]["annotations"] == rows * 2
    assert metrics["molecule_import"]["inserted_rows"] == rows
    assert metrics["annotation_import"]["inserted_rows"] == rows * 2
    assert metrics["molecule_import"]["rows_per_second"] > 0
    assert metrics["annotation_import"]["rows_per_second"] > 0
    assert metrics["cross_query"]["returned_rows"] > 0
    assert metrics["cross_query"]["p95_ms"] >= 0
    assert metrics["resources"]["database_bytes"] > 0
    assert metrics["resources"]["peak_process_rss_bytes"] > 0
