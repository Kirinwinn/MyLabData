"""Shared pytest configuration and opt-in benchmark controls."""

import os
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-performance",
        action="store_true",
        default=False,
        help="run real-scale performance benchmarks",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    run_performance = (
        config.getoption("--run-performance") or os.getenv("MLD_RUN_PERFORMANCE") == "1"
    )
    skip_performance = pytest.mark.skip(
        reason="performance benchmark is opt-in; pass --run-performance"
    )
    for item in items:
        parts = Path(str(item.path)).parts
        if "performance" in parts:
            item.add_marker(pytest.mark.performance)
            if not run_performance:
                item.add_marker(skip_performance)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
