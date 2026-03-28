"""Dry SMILES table acquisition tool.

Merge csv/xlsx table files into one parquet file with a single `SMILES` column.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


SUPPORTED_TABLE_EXTENSIONS = {".csv", ".xlsx"}


def _read_first_smiles_column(file_path: Path) -> pd.DataFrame:
    """Read only the first column and validate it is named `SMILES`."""
    if file_path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(file_path, usecols=[0], encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, usecols=[0], encoding="gbk")
    else:
        excel = pd.ExcelFile(file_path)
        if len(excel.sheet_names) != 1:
            raise ValueError(
                f"xlsx must contain exactly one sheet, got {len(excel.sheet_names)}"
            )
        df = excel.parse(excel.sheet_names[0], usecols=[0])

    if len(df.columns) == 0:
        raise ValueError("table has no columns")

    first_col = str(df.columns[0]).strip()
    if first_col != "SMILES":
        raise ValueError(f"first column header must be 'SMILES', got '{first_col}'")

    smiles = df.iloc[:, 0].dropna().astype(str).str.strip()
    smiles = smiles[smiles != ""]
    return pd.DataFrame({"SMILES": smiles})


def _collect_table_files(input_path: Path) -> List[Path]:
    """Collect csv/xlsx files from a file path or a directory."""
    if not input_path.exists():
        return []

    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in SUPPORTED_TABLE_EXTENSIONS else []

    files: List[Path] = []
    for ext in SUPPORTED_TABLE_EXTENSIONS:
        files.extend(sorted(input_path.glob(f"*{ext}")))
    return sorted(files)


def run(
    input_path: str,
    output_parquet_path: str,
) -> Dict[str, Any]:
    """Merge csv/xlsx SMILES tables and export one parquet file.

    Input rules:
    - Only `.csv` and `.xlsx` are accepted.
    - First column header must be exactly `SMILES`.
    """
    source = Path(input_path)
    output = Path(output_parquet_path)

    table_files = _collect_table_files(source)
    if not table_files:
        return {
            "status": "error",
            "input_path": input_path,
            "output_parquet_path": output_parquet_path,
            "messages": ["No csv/xlsx files found in input path."],
        }

    merged_parts: List[pd.DataFrame] = []
    per_file_counts: Dict[str, int] = {}

    try:
        for file_path in table_files:
            part = _read_first_smiles_column(file_path)
            merged_parts.append(part)
            per_file_counts[file_path.name] = int(len(part))
    except Exception as exc:
        return {
            "status": "error",
            "input_path": input_path,
            "output_parquet_path": output_parquet_path,
            "messages": [f"Failed while reading '{file_path.name}': {exc}"],
        }

    merged = pd.concat(merged_parts, ignore_index=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output, index=False)

    return {
        "status": "success",
        "input_path": input_path,
        "output_parquet_path": output_parquet_path,
        "files_processed": len(table_files),
        "row_count": int(len(merged)),
        "columns": ["SMILES"],
        "per_file_counts": per_file_counts,
        "messages": ["Merged csv/xlsx tables into a single parquet file."],
    }


if __name__ == "__main__":
    import json
    # Input: RO directory or single csv/xlsx file
    # Output: merged RW parquet
    INPUT_PATH = r"E:\DryData\Generated\BatchG004RO"
    OUTPUT_PARQUET_PATH = r"E:\DryData\Generated\BatchG004RW.parquet"
    result = run(INPUT_PATH, OUTPUT_PARQUET_PATH)
    print(json.dumps(result, ensure_ascii=False, indent=2))
