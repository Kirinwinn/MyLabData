"""Dry ViewMode backend logic (v2).

Hybrid architecture:
  - Info table in Dry.db:  (LabID, BatchID, SMILES) for molecule registration
  - _Batches table in Dry.db: batch metadata
  - Property/*.parquet: Trait data (read directly from Parquet, not in SQLite)

Completely independent from Wet ViewMode - no shared functions.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# Import centralized paths from pipeline config
try:
    from Database.Dry import DRY_DATA_ROOT, DRY_DB_PATH
except ImportError:
    DRY_DB_PATH = Path(os.getenv("DRY_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "Database" / "Dry" / "Dry.db")))
    DRY_DATA_ROOT = Path(os.getenv("DRY_DATA_ROOT", r"E:\DryData"))

# Trait definitions
TRAIT_COLUMNS = [f"Trait{i}" for i in range(1, 45)]

TRAIT_LABELS = {
    "Trait1": "Hydroxyl group",
    "Trait2": "Thiol group",
    "Trait3": "Thioether group",
    "Trait4": "Nitro group",
    "Trait5": "Nitroso group",
    "Trait6": "Azo group",
    "Trait7": "Diazo group",
    "Trait8": "Aldehyde group",
    "Trait9": "Carbonyl/Ketone group",
    "Trait10": "Carboxyl group",
    "Trait11": "Ester group",
    "Trait12": "Cyano group",
    "Trait13": "Thiocarbonyl group",
    "Trait14": "Acyl halide group",
    "Trait15": "Acid anhydride group",
    "Trait16": "Heavy atom (I/Br)",
    "Trait17": "Alkynyl group",
    "Trait18": "Sulfonic acid group",
    "Trait19": "Quaternary ammonium group",
    "Trait20": "Phosphate group",
    "Trait21": "Boronic acid group",
    "Trait22": "Isothiocyanate group",
    "Trait23": "Azide group",
    "Trait24": "Succinimidyl ester group",
    "Trait25": "Molecular Weight",
    "Trait26": "LogP",
    "Trait27": "LogD",
    "Trait28": "LogS",
    "Trait29": "Aromaticity",
    "Trait30": "TPSA",
    "Trait31": "Fsp3",
    "Trait32": "Rotatable Bonds",
    "Trait33": "Aromatic Rings",
    "Trait34": "Aliphatic Rings",
    "Trait35": "Atomic Connectivity",
    "Trait36": "Longest Conjugated Length",
    "Trait37": "Molar Refractivity",
    "Trait38": "Molecular Volume",
    "Trait39": "H-bond Acceptors",
    "Trait40": "H-bond Donors",
    "Trait41": "Formal Charge",
    "Trait42": "Dipole Moment",
    "Trait43": "Topological Polarizability",
    "Trait44": "pKa",
}

TRAIT_CATEGORIES = {
    "function_groups": list(range(1, 25)),
    "basic_property": list(range(25, 30)),
    "space_property": list(range(30, 39)),
    "electron_property": list(range(39, 45)),
}

# Whether a trait is integer-valued or continuous
# integer: functional group counts, ring counts, bond counts, etc.
# continuous: MW, LogP, TPSA, Fsp3, etc.
TRAIT_TYPES = {
    "Trait1": "integer", "Trait2": "integer", "Trait3": "integer",
    "Trait4": "integer", "Trait5": "integer", "Trait6": "integer",
    "Trait7": "integer", "Trait8": "integer", "Trait9": "integer",
    "Trait10": "integer", "Trait11": "integer", "Trait12": "integer",
    "Trait13": "integer", "Trait14": "integer", "Trait15": "integer",
    "Trait16": "integer", "Trait17": "integer", "Trait18": "integer",
    "Trait19": "integer", "Trait20": "integer", "Trait21": "integer",
    "Trait22": "integer", "Trait23": "integer", "Trait24": "integer",
    "Trait25": "continuous",  # Molecular Weight
    "Trait26": "continuous",  # LogP
    "Trait27": "continuous",  # LogD
    "Trait28": "continuous",  # LogS
    "Trait29": "continuous",  # Aromaticity
    "Trait30": "continuous",  # TPSA
    "Trait31": "continuous",  # Fsp3
    "Trait32": "integer",     # Rotatable Bonds
    "Trait33": "integer",     # Aromatic Rings
    "Trait34": "integer",     # Aliphatic Rings
    "Trait35": "integer",     # Atomic Connectivity
    "Trait36": "integer",     # Longest Conjugated Length
    "Trait37": "continuous",  # Molar Refractivity
    "Trait38": "continuous",  # Molecular Volume
    "Trait39": "integer",     # H-bond Acceptors
    "Trait40": "integer",     # H-bond Donors
    "Trait41": "integer",     # Formal Charge
    "Trait42": "continuous",  # Dipole Moment
    "Trait43": "continuous",  # Topological Polarizability
    "Trait44": "continuous",  # pKa
}

PREDICTION_MODELS = [
    "Proby",
    "FLAME",
    "Tox21",
    "DeepChemStable",
    "editretro",
    "rxn4chemistry",
]

# Active prediction models (those with actual data support)
from Database.Tools.Dry.Dry_Prediction import ACTIVE_MODELS as _ACTIVE_PRED_MODELS


def get_dry_connection(db_path: str | Path = DRY_DB_PATH) -> sqlite3.Connection:
    """Get a connection to Dry.db with row factory enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────
#  Batch listing and info
# ─────────────────────────────────────────────────

def list_dry_batches(db_path: str | Path = DRY_DB_PATH) -> List[Dict[str, Any]]:
    """Get list of all batches from _Batches table."""
    conn = get_dry_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT batch_code, source_type, molecule_count,
                   created_at, updated_at
            FROM _Batches
            ORDER BY batch_code
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_dry_batch_by_code(batch_code: str, db_path: str | Path = DRY_DB_PATH) -> Optional[Dict[str, Any]]:
    """Get batch info by batch_code."""
    conn = get_dry_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT batch_code, source_type, molecule_count,
                   created_at, updated_at
            FROM _Batches
            WHERE batch_code = ?
            """,
            (batch_code,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_dry_batch_stats(batch_code: str, db_path: str | Path = DRY_DB_PATH) -> Dict[str, Any]:
    """Get statistics for a batch from Info table."""
    conn = get_dry_connection(db_path)
    try:
        # Total molecules in this batch
        total_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM Info WHERE BatchID LIKE ?",
            (f"{batch_code}%",)
        ).fetchone()
        total_count = total_row["cnt"] if total_row else 0

        # Unique to this batch: SMILES that appear in only one batch
        unique_row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM Info i1
            WHERE i1.BatchID LIKE ?
            AND NOT EXISTS (
                SELECT 1 FROM Info i2
                WHERE i2.SMILES = i1.SMILES
                AND i2.BatchID NOT LIKE ?
            )
            """,
            (f"{batch_code}%", f"{batch_code}%")
        ).fetchone()
        unique_count = unique_row["cnt"] if unique_row else 0

        return {
            "batch_code": batch_code,
            "count": total_count,
            "validity": {
                "count": total_count,
                "ratio": 1.0,
            },
            "uniqueness": {
                "count": unique_count,
                "ratio": round(unique_count / total_count, 4) if total_count > 0 else 0.0,
            },
        }
    finally:
        conn.close()


def get_all_batches_stats(db_path: str | Path = DRY_DB_PATH) -> Dict[str, Any]:
    """Get aggregated stats across ALL batches (for the 'All' pseudo-batch)."""
    conn = get_dry_connection(db_path)
    try:
        total_row = conn.execute("SELECT COUNT(*) as cnt FROM Info").fetchone()
        total_count = total_row["cnt"] if total_row else 0

        unique_row = conn.execute(
            "SELECT COUNT(DISTINCT SMILES) as cnt FROM Info"
        ).fetchone()
        unique_smiles = unique_row["cnt"] if unique_row else 0

        batch_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM _Batches"
        ).fetchone()
        batch_count = batch_row["cnt"] if batch_row else 0

        return {
            "batch_code": "All",
            "count": total_count,
            "unique_smiles": unique_smiles,
            "batch_count": batch_count,
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────
#  Trait distribution for dynamic chart
# ─────────────────────────────────────────────────

def get_property_file_path(batch_code: str) -> Optional[Path]:
    """Get the Property parquet file path for a batch."""
    property_dir = DRY_DATA_ROOT / "Property"
    property_file = property_dir / f"{batch_code}.parquet"
    if property_file.exists():
        return property_file
    return None


def get_all_property_files() -> List[Path]:
    """Get all Property parquet files for 'All' batch aggregation."""
    property_dir = DRY_DATA_ROOT / "Property"
    if not property_dir.exists():
        return []
    return list(property_dir.glob("*.parquet"))


def get_trait_distribution(
    batch_code: str,
    trait: str,
    bins: int = 50,
    db_path: str | Path = DRY_DB_PATH,
) -> Dict[str, Any]:
    """Calculate distribution of a trait for a batch from Property parquet."""
    if trait not in TRAIT_COLUMNS:
        return {"error": f"Invalid trait: {trait}"}

    # Handle 'All' pseudo-batch: merge all Property parquet files
    if batch_code == "All":
        all_files = get_all_property_files()
        if not all_files:
            return {"error": "No Property files found"}
        
        dfs = []
        for pf in all_files:
            try:
                df_part = pd.read_parquet(pf, columns=["SMILES", trait])
                dfs.append(df_part)
            except Exception:
                continue
        
        if not dfs:
            return {"error": "Failed to read any Property files"}
        
        df = pd.concat(dfs, ignore_index=True)
    else:
        property_file = get_property_file_path(batch_code)
        if not property_file:
            return {"error": f"Property file not found for {batch_code}"}

        try:
            df = pd.read_parquet(property_file, columns=["SMILES", trait])
        except Exception as e:
            return {"error": f"Failed to read property file: {e}"}

    df = df.dropna(subset=[trait])
    df[trait] = pd.to_numeric(df[trait], errors="coerce")
    df = df.dropna(subset=[trait])

    if len(df) == 0:
        return {
            "trait": trait,
            "trait_label": TRAIT_LABELS.get(trait, trait),
            "batch_code": batch_code,
            "total_count": 0,
            "bins": [],
        }

    values = df[trait].values
    smiles_list = df["SMILES"].tolist()
    trait_type = TRAIT_TYPES.get(trait, "continuous")

    min_val = float(np.min(values))
    max_val = float(np.max(values))

    if trait_type == "integer":
        # Integer-valued trait: one bin per integer value
        int_min = int(np.floor(min_val))
        int_max = int(np.ceil(max_val))
        hist_bins = []
        for iv in range(int_min, int_max + 1):
            mask = (values >= iv - 0.5) & (values < iv + 0.5)
            bin_count = int(np.sum(mask))
            bin_smiles = [s for s, m in zip(smiles_list, mask) if m]
            hist_bins.append({
                "min": iv,
                "max": iv,
                "count": bin_count,
                "label": str(iv),
                "smiles": bin_smiles,
            })
    elif max_val == min_val:
        hist_bins = [{"min": min_val, "max": max_val, "count": len(values), "smiles": smiles_list}]
    else:
        bin_edges = np.linspace(min_val, max_val, bins + 1)
        hist_bins = []

        for i in range(len(bin_edges) - 1):
            bin_min = float(bin_edges[i])
            bin_max = float(bin_edges[i + 1])

            if i == len(bin_edges) - 2:
                mask = (values >= bin_min) & (values <= bin_max)
            else:
                mask = (values >= bin_min) & (values < bin_max)

            bin_count = int(np.sum(mask))
            bin_smiles = [s for s, m in zip(smiles_list, mask) if m]

            hist_bins.append({
                "min": round(bin_min, 4),
                "max": round(bin_max, 4),
                "count": bin_count,
                "smiles": bin_smiles,
            })

    # Find peak center for tick interval calculation
    peak_bin = max(hist_bins, key=lambda b: b["count"]) if hist_bins else None
    if trait_type == "integer":
        peak_center = peak_bin["min"] if peak_bin else 0
        tick_interval = 1
    else:
        peak_center = (peak_bin["min"] + peak_bin["max"]) / 2 if peak_bin else 0
        tick_interval = round(abs(peak_center) * 0.1, 4) if peak_center != 0 else round((max_val - min_val) / 10, 4)

    return {
        "trait": trait,
        "trait_label": TRAIT_LABELS.get(trait, trait),
        "trait_type": trait_type,
        "batch_code": batch_code,
        "total_count": len(df),
        "min_value": round(min_val, 4),
        "max_value": round(max_val, 4),
        "mean_value": round(float(np.mean(values)), 4),
        "std_value": round(float(np.std(values)), 4),
        "peak_center": round(peak_center, 4),
        "tick_interval": tick_interval,
        "bins": hist_bins,
    }


def get_trait_distribution_simple(
    batch_code: str,
    trait: str,
    bins: int = 50,
) -> Dict[str, Any]:
    """Get trait distribution without SMILES lists (for chart rendering)."""
    result = get_trait_distribution(batch_code, trait, bins)

    if "error" in result:
        return result

    simple_bins = []
    for b in result.get("bins", []):
        simple_bins.append({
            "min": b["min"],
            "max": b["max"],
            "count": b["count"],
        })

    result["bins"] = simple_bins
    return result


# ─────────────────────────────────────────────────
#  Molecule queries by range
# ─────────────────────────────────────────────────

def get_molecules_by_trait_range(
    batch_code: str,
    trait: str,
    min_value: float,
    max_value: float,
    limit: int = 100,
    db_path: str | Path = DRY_DB_PATH,
) -> Dict[str, Any]:
    """Get molecules within a trait value range from Property parquet."""
    if trait not in TRAIT_COLUMNS:
        return {"error": f"Invalid trait: {trait}"}

    # Handle 'All' pseudo-batch: merge all Property parquet files
    if batch_code == "All":
        all_files = get_all_property_files()
        if not all_files:
            return {"error": "No Property files found"}
        
        dfs = []
        for pf in all_files:
            try:
                df_part = pd.read_parquet(pf, columns=["SMILES", trait])
                dfs.append(df_part)
            except Exception:
                continue
        
        if not dfs:
            return {"error": "Failed to read any Property files"}
        
        df = pd.concat(dfs, ignore_index=True)
    else:
        property_file = get_property_file_path(batch_code)
        if not property_file:
            return {"error": f"Property file not found for {batch_code}"}

        try:
            df = pd.read_parquet(property_file, columns=["SMILES", trait])
        except Exception as e:
            return {"error": f"Failed to read property file: {e}"}

    df = df.dropna(subset=[trait])
    df[trait] = pd.to_numeric(df[trait], errors="coerce")
    df = df.dropna(subset=[trait])
    df = df[(df[trait] >= min_value) & (df[trait] <= max_value)]

    total_in_range = len(df)

    if limit and limit > 0:
        df = df.head(limit)

    # Get LabIDs by querying Info table with SMILES
    smiles_list = df["SMILES"].tolist()
    lab_id_map = {}
    
    if smiles_list:
        conn = get_dry_connection(db_path)
        try:
            # Query LabID for each SMILES
            placeholders = ",".join(["?"] * len(smiles_list))
            rows = conn.execute(
                f"SELECT SMILES, LabID FROM Info WHERE SMILES IN ({placeholders})",
                smiles_list
            ).fetchall()
            for row in rows:
                lab_id_map[row["SMILES"]] = row["LabID"]
        finally:
            conn.close()

    molecules = []
    for _, row in df.iterrows():
        smiles = str(row["SMILES"])
        molecules.append({
            "lab_id": lab_id_map.get(smiles, "Unknown"),
            "smiles": smiles,
            "value": round(float(row[trait]), 4),
        })

    return {
        "batch_code": batch_code,
        "trait": trait,
        "trait_label": TRAIT_LABELS.get(trait, trait),
        "min_value": min_value,
        "max_value": max_value,
        "total_in_range": total_in_range,
        "returned_count": len(molecules),
        "molecules": molecules,
    }


# ─────────────────────────────────────────────────
#  Molecule info by LabID or BatchID
# ─────────────────────────────────────────────────

def get_molecule_by_lab_id(
    lab_id: str,
    db_path: str | Path = DRY_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Get molecule info by global LabID (e.g., L00000001)."""
    conn = get_dry_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT LabID, BatchID, SMILES FROM Info WHERE LabID = ?",
            (lab_id,)
        ).fetchall()
        if not rows:
            return None
        return {
            "lab_id": rows[0]["LabID"],
            "smiles": rows[0]["SMILES"],
            "batch_ids": [r["BatchID"] for r in rows],
            "batch_count": len(rows),
        }
    finally:
        conn.close()


def get_molecule_by_batch_id(
    batch_id: str,
    db_path: str | Path = DRY_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Get molecule info by BatchID (e.g., BatchE0010000001)."""
    conn = get_dry_connection(db_path)
    try:
        row = conn.execute(
            "SELECT LabID, BatchID, SMILES FROM Info WHERE BatchID = ?",
            (batch_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_batch_molecule_list(
    batch_code: str,
    offset: int = 0,
    limit: int = 100,
    db_path: str | Path = DRY_DB_PATH,
) -> Dict[str, Any]:
    """Get paginated list of molecules in a batch."""
    conn = get_dry_connection(db_path)
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM Info WHERE BatchID LIKE ?",
            (f"{batch_code}%",)
        ).fetchone()
        total_count = total_row["cnt"] if total_row else 0

        rows = conn.execute(
            """
            SELECT LabID, BatchID, SMILES
            FROM Info
            WHERE BatchID LIKE ?
            ORDER BY BatchID
            LIMIT ? OFFSET ?
            """,
            (f"{batch_code}%", limit, offset)
        ).fetchall()

        return {
            "batch_code": batch_code,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "molecules": [dict(row) for row in rows],
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────
#  Trait metadata
# ─────────────────────────────────────────────────

def get_trait_info() -> Dict[str, Any]:
    """Get all trait metadata for UI rendering."""
    categories = {}

    for cat_name, trait_nums in TRAIT_CATEGORIES.items():
        traits = []
        for num in trait_nums:
            key = f"Trait{num}"
            traits.append({
                "key": key,
                "label": TRAIT_LABELS.get(key, key),
                "type": TRAIT_TYPES.get(key, "continuous"),
            })
        categories[cat_name] = traits

    return {
        "categories": categories,
        "prediction_models": PREDICTION_MODELS,
    }


# ─────────────────────────────────────────────────
#  Prediction status
# ─────────────────────────────────────────────────

def get_prediction_status(
    batch_code: str,
    db_path: str | Path = DRY_DB_PATH,
) -> Dict[str, Any]:
    """Check which prediction models have results for a batch."""
    from Database.Tools.Dry.Dry_Prediction import get_prediction_availability

    availability = get_prediction_availability(batch_code)
    # Merge active model availability with full model list
    models: Dict[str, bool] = {}
    for m in PREDICTION_MODELS:
        models[m] = availability.get(m, False)
    return {
        "batch_code": batch_code,
        "models": models,
    }
