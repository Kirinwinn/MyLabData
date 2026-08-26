"""Verify the completed BuExperimentData to ExperiData migration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .Registry import DryRegistry, _rows_as_dicts


def verify(registry: DryRegistry | None = None) -> dict[str, Any]:
    registry = registry or DryRegistry()
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    connection = registry.connect(read_only=True)
    try:
        imports = _rows_as_dicts(connection.execute(
            """
            SELECT import_id, data_category, source_class, input_path,
                   processed_path, checksum_sha256, status, total_rows
            FROM Imports ORDER BY import_id
            """
        ))
        views = [
            row[0]
            for row in connection.execute(
                """
                SELECT view_name FROM duckdb_views()
                WHERE schema_name = 'main' AND internal = false
                ORDER BY view_name
                """
            ).fetchall()
        ]
        counts = {
            table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
            for table in ("Molecules", "Attributes", "Sources", "Imports")
        }
        view_counts = {
            view: int(connection.execute(f'SELECT count(*) FROM "{view}"').fetchone()[0])
            for view in ("TraitValues", "DeepMPPValues", "ProbyValues", "Tox21Values")
            if view in views
        }
        trait_sample = _rows_as_dicts(connection.execute(
            """
            SELECT lab_id, SMILES, MW, calc_ok
            FROM TraitValues
            WHERE calc_ok = 1
            LIMIT 3
            """
        )) if "TraitValues" in views else []
    finally:
        connection.close()

    for item in imports:
        if item["status"] != "completed":
            errors.append(f"Import {item['import_id']} is {item['status']}")
            continue
        input_path = Path(item["input_path"])
        processed_path = Path(item["processed_path"])
        if not input_path.is_file():
            errors.append(f"Missing source file: {input_path}")
        if not processed_path.is_file():
            errors.append(f"Missing processed file: {processed_path}")
            continue
        parquet = pq.ParquetFile(processed_path)
        rows = parquet.metadata.num_rows
        columns = parquet.schema_arrow.names
        if rows != item["total_rows"]:
            errors.append(
                f"Row mismatch for {processed_path}: import={item['total_rows']}, parquet={rows}"
            )
        if item["data_category"] != "molecules" and "lab_id" not in columns:
            errors.append(f"Missing lab_id in {processed_path}")
        if not item["checksum_sha256"] or len(item["checksum_sha256"]) != 64:
            errors.append(f"Missing checksum for import {item['import_id']}")
        files.append({
            "import_id": item["import_id"],
            "category": item["data_category"],
            "source_class": item["source_class"],
            "path": str(processed_path),
            "rows": rows,
            "size_bytes": processed_path.stat().st_size,
            "columns": len(columns),
        })

    expected_views = {"TraitValues", "DeepMPPValues", "ProbyValues", "Tox21Values"}
    missing_views = expected_views - set(views)
    if missing_views:
        errors.append(f"Missing views: {sorted(missing_views)}")

    temporary_files = list(registry.dry_root.rglob("*.tmp")) + list(
        registry.dry_root.rglob("*.tmp.parquet")
    )
    if temporary_files:
        errors.append(f"Temporary files remain: {[str(path) for path in temporary_files]}")

    return {
        "ok": not errors,
        "errors": errors,
        "counts": counts,
        "views": views,
        "view_counts": view_counts,
        "trait_sample": trait_sample,
        "files": files,
    }


def main() -> None:
    report = verify()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
