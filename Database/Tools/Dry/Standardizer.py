"""Dry SMILES standardizer and desalting tool.

Workflow:
1) Read one RW parquet file containing `SMILES` column.
2) Validate and canonicalize SMILES.
3) Desalt canonical SMILES in memory.
4) Output a single formal parquet in Separate style (one `SMILES` column).

No intermediate files are written to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from rdkit import Chem
from rdkit import rdBase

rdBase.DisableLog("rdApp.error")


NON_METALLIC_IONS_SMILES = {
    "[F-]",
    "[Cl-]",
    "[Br-]",
    "[I-]",
    "[OH-]",
    "S(=O)(=O)([O-])[O-]",
    "[O-]S(=O)(=O)O",
    "[Co+]",
    "[O-][N+](=O)[O-]",
    "O=[N+][O-]",
    "OP(=O)([O-])[O-]",
    "O=P([O-])([O-])O",
    "OP(=O)(O)O",
    "[NH4+]",
    "[OH3+]",
    "CC(=O)[O-]",
    "C(=O)[O-]",
}

METAL_ATOMIC_NUMS = {
    3,
    4,
    11,
    12,
    13,
    19,
    20,
    26,
    27,
    28,
    29,
    30,
    31,
    37,
    38,
    47,
    50,
    55,
    56,
    78,
    79,
    80,
    82,
    83,
}


def _clean_smiles_extension(smiles: str) -> str:
    """Remove known `jcExt` suffix from vendor strings."""
    if "jcExt" in smiles:
        return smiles.split("jcExt")[0]
    return smiles


def _build_non_metallic_ions_set() -> set[str]:
    """Canonical set for quickly identifying removable ionic fragments."""
    ion_set: set[str] = set()
    for ion in NON_METALLIC_IONS_SMILES:
        mol = Chem.MolFromSmiles(ion)
        if mol is not None:
            ion_set.add(Chem.MolToSmiles(mol))
    return ion_set


def _validate_rw_input(df: pd.DataFrame) -> None:
    """Ensure RW dataframe has first column named `SMILES`."""
    if df.empty and len(df.columns) == 0:
        raise ValueError("RW parquet is empty with no columns")

    first_col = str(df.columns[0]).strip()
    if first_col != "SMILES":
        raise ValueError(f"First column must be 'SMILES', got '{first_col}'")


def _canonicalize_smiles(raw_smiles: List[str]) -> tuple[List[str], List[str]]:
    """Return (valid_canonical_smiles, invalid_smiles)."""
    valid: List[str] = []
    invalid: List[str] = []

    for smi in raw_smiles:
        cleaned = _clean_smiles_extension(smi)
        try:
            mol = Chem.MolFromSmiles(cleaned)
            if mol is None:
                invalid.append(smi)
            else:
                valid.append(Chem.MolToSmiles(mol))
        except Exception:
            invalid.append(smi)

    return valid, invalid


def _desalt_smiles(canonical_smiles: List[str]) -> List[str]:
    """Desalt canonical SMILES and keep the main non-ionic fragment."""
    non_metal_ions = _build_non_metallic_ions_set()
    desalted: List[str] = []

    for smiles in canonical_smiles:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue

            frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
            if len(frags) <= 1:
                desalted.append(smiles)
                continue

            valid_frags = [
                frag
                for frag in frags
                if not (
                    frag.GetNumAtoms() == 1
                    and frag.GetAtomWithIdx(0).GetAtomicNum() in METAL_ATOMIC_NUMS
                )
                and Chem.MolToSmiles(frag) not in non_metal_ions
            ]

            if valid_frags:
                # Keep the largest retained fragment as the main molecule.
                main_frag = max(valid_frags, key=lambda m: m.GetNumAtoms())
                desalted.append(Chem.MolToSmiles(main_frag))
        except Exception:
            continue

    return desalted


def run(
    input_file: str,
    output_dir: str,
    output_format: str = "parquet",
) -> Dict[str, Any]:
    """Standardize and desalt an RW parquet file.

    Args:
        input_file: Path to `Batch*RW.parquet`.
        output_dir: Directory for formal Separate output.
        output_format: Currently only `parquet` is supported.
    """
    input_path = Path(input_file)
    output_path_dir = Path(output_dir)

    if output_format.lower() != "parquet":
        return {
            "status": "error",
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "messages": ["Only 'parquet' output is supported for Separate stage."],
        }

    if not input_path.exists():
        return {
            "status": "error",
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "messages": [f"Input file not found: {input_file}"],
        }

    if input_path.suffix.lower() != ".parquet":
        return {
            "status": "error",
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "messages": ["Input must be a parquet file."],
        }

    try:
        df_input = pd.read_parquet(input_path)
        _validate_rw_input(df_input)
    except Exception as exc:
        return {
            "status": "error",
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "messages": [f"Failed to load RW input: {exc}"],
        }

    raw_smiles = (
        df_input.iloc[:, 0].dropna().astype(str).str.strip().loc[lambda s: s != ""].tolist()
    )
    valid_canonical, invalid = _canonicalize_smiles(raw_smiles)

    desalted_list = _desalt_smiles(valid_canonical)
    df_final = pd.DataFrame({"SMILES": pd.Series(desalted_list, dtype="string")}).dropna()
    df_final = df_final[df_final["SMILES"].str.strip() != ""]
    df_final = df_final.drop_duplicates().reset_index(drop=True)

    base = input_path.stem
    formal_base = base[:-2] if base.endswith("RW") else base
    output_path_dir.mkdir(parents=True, exist_ok=True)
    formal_output = output_path_dir / f"{formal_base}.parquet"

    try:
        df_final.to_parquet(formal_output, index=False)
    except Exception as exc:
        return {
            "status": "error",
            "input_file": input_file,
            "output_dir": output_dir,
            "output_format": output_format,
            "messages": [f"Failed to write output parquet: {exc}"],
        }

    return {
        "status": "success",
        "input_file": input_file,
        "output_dir": output_dir,
        "output_format": output_format,
        "output_file": str(formal_output),
        "input_count": len(raw_smiles),
        "valid_count": len(valid_canonical),
        "invalid_count": len(invalid),
        "desalted_count": len(desalted_list),
        "final_unique_count": int(len(df_final)),
        "invalid_examples": invalid[:20],
        "messages": [
            "Standardization and desalting completed.",
            "No intermediate files were written.",
        ],
    }


if __name__ == "__main__":
    import json
    # Input: RW parquet file
    # Output: Separate parquet in OUTPUT_DIR
    INPUT_FILE = r"E:\ExperimentData\DryData\External\BatchE024RW.parquet"
    OUTPUT_DIR = r"E:\ExperimentData\DryData\Separate"
    OUTPUT_FORMAT = "parquet"
    result = run(INPUT_FILE, OUTPUT_DIR, OUTPUT_FORMAT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
