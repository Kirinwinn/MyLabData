"""Dry CompareMode backend logic.

Provides search, trait lookup, and data packaging for the Compare panel.
Reuses DB paths and trait definitions from Dry_ViewMode.
"""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any, Dict, List, Optional

import pandas as pd

from Search.Dry_ViewMode import (
    DRY_DATA_ROOT,
    DRY_DB_PATH,
    PREDICTION_MODELS,
    TRAIT_CATEGORIES,
    TRAIT_COLUMNS,
    TRAIT_LABELS,
    TRAIT_TYPES,
    get_all_property_files,
    get_dry_connection,
    get_property_file_path,
)


def search_molecule(query: str) -> Optional[Dict[str, Any]]:
    """Search for a molecule by LabID or SMILES.

    Priority: LabID exact match → SMILES exact match.
    Returns full molecule info dict or None.
    """
    query = query.strip()
    if not query:
        return None

    conn = get_dry_connection()
    try:
        # 1. Try LabID exact match
        rows = conn.execute(
            "SELECT LabID, BatchID, SMILES FROM Info WHERE LabID = ?",
            (query,),
        ).fetchall()

        if not rows:
            # 2. Try SMILES exact match
            rows = conn.execute(
                "SELECT LabID, BatchID, SMILES FROM Info WHERE SMILES = ?",
                (query,),
            ).fetchall()

        if not rows:
            return None

        lab_id = rows[0]["LabID"]
        smiles = rows[0]["SMILES"]
        batch_ids = [r["BatchID"] for r in rows]

        # Derive batch_codes from batch_ids (e.g. "BatchE0010000001" → "BatchE001")
        batch_codes = sorted(set(_batch_code_from_id(bid) for bid in batch_ids))

        # Get batch created_at from _Batches
        created_at = None
        if batch_codes:
            bat_row = conn.execute(
                "SELECT created_at FROM _Batches WHERE batch_code = ?",
                (batch_codes[0],),
            ).fetchone()
            if bat_row:
                created_at = bat_row["created_at"]

        # Load traits
        traits = _load_traits_for_smiles(smiles, batch_codes)

        # Load real prediction data
        from Database.Tools.Dry.Dry_Prediction import get_molecule_predictions
        predictions = get_molecule_predictions(smiles, batch_codes)

        return {
            "lab_id": lab_id,
            "smiles": smiles,
            "batch_ids": batch_ids,
            "batch_codes": batch_codes,
            "created_at": created_at or "-",
            "traits": traits,
            "predictions": predictions,
        }
    finally:
        conn.close()


def _batch_code_from_id(batch_id: str) -> str:
    """Extract batch_code from a BatchID string.

    e.g. 'BatchE0010000001' → 'BatchE001'
    """
    # BatchID format: {batch_code}{7-digit serial}
    if len(batch_id) > 7:
        return batch_id[:-7]
    return batch_id


def _load_traits_for_smiles(
    smiles: str, batch_codes: List[str]
) -> Dict[str, Any]:
    """Load all 44 trait values for a SMILES from Property parquet files."""
    # Try each batch's parquet file
    for bc in batch_codes:
        pf = get_property_file_path(bc)
        if pf is None:
            continue
        try:
            df = pd.read_parquet(pf)
            row = df[df["SMILES"] == smiles]
            if len(row) > 0:
                result = {}
                for col in TRAIT_COLUMNS:
                    val = row.iloc[0].get(col)
                    if pd.isna(val):
                        result[col] = None
                    else:
                        result[col] = round(float(val), 4)
                return result
        except Exception:
            continue

    # Fallback: search all parquet files
    for pf in get_all_property_files():
        try:
            df = pd.read_parquet(pf)
            row = df[df["SMILES"] == smiles]
            if len(row) > 0:
                result = {}
                for col in TRAIT_COLUMNS:
                    val = row.iloc[0].get(col)
                    if pd.isna(val):
                        result[col] = None
                    else:
                        result[col] = round(float(val), 4)
                return result
        except Exception:
            continue

    return {col: None for col in TRAIT_COLUMNS}


def get_trait_categories_with_values(
    traits: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Organize trait values into categories for list display."""
    categories = {}
    for cat_name, trait_nums in TRAIT_CATEGORIES.items():
        items = []
        for num in trait_nums:
            key = f"Trait{num}"
            items.append({
                "key": key,
                "label": TRAIT_LABELS.get(key, key),
                "type": TRAIT_TYPES.get(key, "continuous"),
                "value": traits.get(key),
            })
        categories[cat_name] = items
    return categories


def package_molecule_data(lab_id: str, smiles: str, traits: Dict[str, Any]) -> io.BytesIO:
    """Create a zip archive containing molecule data in memory.

    Contents:
      - {lab_id}_info.txt   : metadata
      - {lab_id}_traits.csv : 44 trait values
    Note: 2D SVG and 3D SDF are generated by the routes in app.py and
    added to the zip there (to keep RDKit dependency out of this module).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # info.txt
        info_lines = [
            f"LabID: {lab_id}",
            f"SMILES: {smiles}",
        ]
        zf.writestr(f"{lab_id}_info.txt", "\n".join(info_lines))

        # traits.csv
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["Trait", "Label", "Type", "Value"])
        for col in TRAIT_COLUMNS:
            writer.writerow([
                col,
                TRAIT_LABELS.get(col, col),
                TRAIT_TYPES.get(col, "continuous"),
                traits.get(col, ""),
            ])
        zf.writestr(f"{lab_id}_traits.csv", csv_buf.getvalue())

    buf.seek(0)
    return buf
