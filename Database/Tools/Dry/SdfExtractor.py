"""Dry SDF SMILES extractor.

Extract SMILES from SDF files and export uniform table files with one column:
`SMILES`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from rdkit import Chem
from rdkit import rdBase

rdBase.DisableLog("rdApp.error")

SUPPORTED_OUTPUT_FORMATS = {"xlsx", "csv"}


def _collect_sdf_files(input_path: Path) -> List[Path]:
    if not input_path.exists():
        return []
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".sdf" else []
    return sorted(input_path.glob("*.sdf"))


def _write_smiles_table(df: pd.DataFrame, output_file: Path, output_format: str) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(output_file, index=False)


def run(input_path: str, output_dir: str, output_format: str = "xlsx") -> Dict[str, Any]:
    """Extract SMILES from SDF files.

    Args:
        input_path: A single `.sdf` path or a directory containing `.sdf` files.
        output_dir: Output directory for generated table files.
        output_format: `xlsx` or `csv`.
    """
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        return {
            "status": "error",
            "messages": [f"Unsupported output_format: {output_format}"],
        }

    source = Path(input_path)
    target_dir = Path(output_dir)
    sdf_files = _collect_sdf_files(source)

    if not sdf_files:
        return {
            "status": "error",
            "input_path": input_path,
            "output_dir": output_dir,
            "messages": ["No .sdf files found in input path."],
        }

    result: Dict[str, Any] = {
        "status": "success",
        "input_path": input_path,
        "output_dir": output_dir,
        "output_format": output_format,
        "files_processed": 0,
        "total_smiles": 0,
        "total_failures": 0,
        "output_files": [],
        "messages": [],
    }

    out_ext = "csv" if output_format == "csv" else "xlsx"

    for sdf_file in sdf_files:
        smiles_rows: List[str] = []
        failure_rows: List[Dict[str, Any]] = []

        supplier = Chem.SDMolSupplier(str(sdf_file), removeHs=False, sanitize=False)
        if supplier is None:
            result["messages"].append(f"Failed to open SDF: {sdf_file.name}")
            continue

        for idx, mol in enumerate(supplier):
            if mol is None:
                failure_rows.append(
                    {
                        "RecordIndex": idx + 1,
                        "Error": "Failed to parse SDF record",
                    }
                )
                continue

            try:
                smiles_rows.append(Chem.MolToSmiles(mol, isomericSmiles=True))
            except Exception as exc:
                failure_rows.append(
                    {
                        "RecordIndex": idx + 1,
                        "Error": f"SMILES conversion failed: {exc}",
                    }
                )

        smiles_df = pd.DataFrame({"SMILES": smiles_rows})
        data_output = target_dir / f"{sdf_file.stem}_smiles.{out_ext}"
        _write_smiles_table(smiles_df, data_output, output_format)

        result["output_files"].append(str(data_output))
        result["files_processed"] += 1
        result["total_smiles"] += len(smiles_rows)
        result["total_failures"] += len(failure_rows)

        if failure_rows:
            result["messages"].append(
                f"{sdf_file.name}: {len(failure_rows)} records failed and were skipped."
            )

    result["messages"].append("SDF extraction completed.")
    return result


if __name__ == "__main__":
    import json
    # Input: single .sdf file or directory containing .sdf files
    # Output: xlsx or csv with SMILES column
    INPUT_PATH = r"E:\DryData\External\BatchE001RO"
    OUTPUT_DIR = r"E:\DryData\_validation\SdfExtract"
    OUTPUT_FORMAT = "csv"
    result = run(INPUT_PATH, OUTPUT_DIR, OUTPUT_FORMAT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
