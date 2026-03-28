"""Dry SearchMode backend logic.

Provides filtered molecule search, distribution, and data packaging.
Independent from ViewMode and CompareMode — no shared function calls at runtime.
Reads directly from Dry.db and Property parquet files.
"""

from __future__ import annotations

import io
import os
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Import centralized paths
try:
    from Database.Dry import DRY_DATA_ROOT, DRY_DB_PATH
except ImportError:
    DRY_DB_PATH = Path(os.getenv("DRY_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "Database" / "Dry" / "Dry.db")))
    DRY_DATA_ROOT = Path(os.getenv("DRY_DATA_ROOT", r"E:\DryData"))

# ── Trait definitions (copied for independence) ──

TRAIT_COLUMNS = [f"Trait{i}" for i in range(1, 45)]

TRAIT_LABELS = {
    "Trait1": "Hydroxyl group", "Trait2": "Thiol group",
    "Trait3": "Thioether group", "Trait4": "Nitro group",
    "Trait5": "Nitroso group", "Trait6": "Azo group",
    "Trait7": "Diazo group", "Trait8": "Aldehyde group",
    "Trait9": "Carbonyl/Ketone group", "Trait10": "Carboxyl group",
    "Trait11": "Ester group", "Trait12": "Cyano group",
    "Trait13": "Thiocarbonyl group", "Trait14": "Acyl halide group",
    "Trait15": "Acid anhydride group", "Trait16": "Heavy atom (I/Br)",
    "Trait17": "Alkynyl group", "Trait18": "Sulfonic acid group",
    "Trait19": "Quaternary ammonium group", "Trait20": "Phosphate group",
    "Trait21": "Boronic acid group", "Trait22": "Isothiocyanate group",
    "Trait23": "Azide group", "Trait24": "Succinimidyl ester group",
    "Trait25": "Molecular Weight", "Trait26": "LogP",
    "Trait27": "LogD", "Trait28": "LogS",
    "Trait29": "Aromaticity", "Trait30": "TPSA",
    "Trait31": "Fsp3", "Trait32": "Rotatable Bonds",
    "Trait33": "Aromatic Rings", "Trait34": "Aliphatic Rings",
    "Trait35": "Atomic Connectivity", "Trait36": "Longest Conjugated Length",
    "Trait37": "Molar Refractivity", "Trait38": "Molecular Volume",
    "Trait39": "H-bond Acceptors", "Trait40": "H-bond Donors",
    "Trait41": "Formal Charge", "Trait42": "Dipole Moment",
    "Trait43": "Topological Polarizability", "Trait44": "pKa",
}

TRAIT_TYPES = {
    "Trait1": "integer", "Trait2": "integer", "Trait3": "integer",
    "Trait4": "integer", "Trait5": "integer", "Trait6": "integer",
    "Trait7": "integer", "Trait8": "integer", "Trait9": "integer",
    "Trait10": "integer", "Trait11": "integer", "Trait12": "integer",
    "Trait13": "integer", "Trait14": "integer", "Trait15": "integer",
    "Trait16": "integer", "Trait17": "integer", "Trait18": "integer",
    "Trait19": "integer", "Trait20": "integer", "Trait21": "integer",
    "Trait22": "integer", "Trait23": "integer", "Trait24": "integer",
    "Trait25": "continuous", "Trait26": "continuous",
    "Trait27": "continuous", "Trait28": "continuous",
    "Trait29": "continuous", "Trait30": "continuous",
    "Trait31": "continuous", "Trait32": "integer",
    "Trait33": "integer", "Trait34": "integer",
    "Trait35": "integer", "Trait36": "integer",
    "Trait37": "continuous", "Trait38": "continuous",
    "Trait39": "integer", "Trait40": "integer",
    "Trait41": "integer", "Trait42": "continuous",
    "Trait43": "continuous", "Trait44": "continuous",
}

TRAIT_CATEGORIES = {
    "function_groups": list(range(1, 25)),
    "basic_property": list(range(25, 30)),
    "space_property": list(range(30, 39)),
    "electron_property": list(range(39, 45)),
}

PREDICTION_MODELS = [
    "Proby", "FLAME", "Tox21",
    "DeepChemStable", "editretro", "rxn4chemistry",
]


# ── helpers ──

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DRY_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _property_dir() -> Path:
    return DRY_DATA_ROOT / "Property"


def _load_parquet_for_batches(batch_codes: List[str], columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Load and concatenate Property parquet files for given batch codes."""
    prop_dir = _property_dir()
    dfs: list[pd.DataFrame] = []

    if not batch_codes:
        # All batches
        if not prop_dir.exists():
            return pd.DataFrame()
        for pf in prop_dir.glob("*.parquet"):
            try:
                dfs.append(pd.read_parquet(pf, columns=columns))
            except Exception:
                continue
    else:
        for bc in batch_codes:
            pf = prop_dir / f"{bc}.parquet"
            if pf.exists():
                try:
                    dfs.append(pd.read_parquet(pf, columns=columns))
                except Exception:
                    continue

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


# ── public API ──

def list_all_batches() -> List[Dict[str, Any]]:
    """Return all batch codes for the Scope selector."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT batch_code, molecule_count FROM _Batches ORDER BY batch_code"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def filter_molecules(
    batch_codes: List[str],
    conditions: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply trait/prediction conditions and return filtered stats.

    conditions example:
        {
            "traits": {
                "Trait25": {"min": 200, "max": 500},
                "Trait1":  {"values": [0, 1]}
            }
        }
    """
    # Load all traits so we can apply conditions
    needed_cols = ["SMILES"] + TRAIT_COLUMNS
    df = _load_parquet_for_batches(batch_codes, columns=needed_cols)

    if df.empty:
        return {"count": 0, "filtered_count": 0, "smiles_list": []}

    total_count = len(df)

    # Apply trait conditions
    trait_conds = conditions.get("traits", {})
    for trait_key, cond in trait_conds.items():
        if trait_key not in TRAIT_COLUMNS:
            continue
        df[trait_key] = pd.to_numeric(df[trait_key], errors="coerce")
        if "min" in cond and cond["min"] is not None:
            df = df[df[trait_key] >= cond["min"]]
        if "max" in cond and cond["max"] is not None:
            df = df[df[trait_key] <= cond["max"]]
        if "values" in cond and cond["values"]:
            df = df[df[trait_key].isin(cond["values"])]

    filtered_count = len(df)
    smiles_list = df["SMILES"].dropna().unique().tolist()

    # Apply prediction conditions (intersection with trait-filtered set)
    pred_conds = conditions.get("predictions", {})
    if pred_conds:
        from Database.Tools.Dry.Dry_Prediction import filter_by_predictions
        pred_smiles = filter_by_predictions(batch_codes, pred_conds)
        if pred_smiles is not None:
            smiles_set = set(smiles_list) & pred_smiles
            smiles_list = list(smiles_set)
            df = df[df["SMILES"].isin(smiles_set)]
            filtered_count = len(df)

    # Compute stats on filtered set
    conn = _get_connection()
    try:
        if smiles_list:
            # Uniqueness: SMILES that appear in only one batch
            placeholders = ",".join(["?"] * min(len(smiles_list), 500))
            chunk = smiles_list[:500]
            unique_row = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM (
                    SELECT SMILES FROM Info
                    WHERE SMILES IN ({placeholders})
                    GROUP BY SMILES
                    HAVING COUNT(DISTINCT substr(BatchID, 1, length(BatchID)-7)) = 1
                )""",
                chunk,
            ).fetchone()
            unique_count = unique_row["cnt"] if unique_row else 0
        else:
            unique_count = 0
    finally:
        conn.close()

    return {
        "total_count": total_count,
        "filtered_count": filtered_count,
        "unique_count": unique_count,
        "unique_ratio": round(unique_count / filtered_count, 4) if filtered_count > 0 else 0,
    }


def get_filtered_distribution(
    batch_codes: List[str],
    conditions: Dict[str, Any],
    trait: str,
    bins: int = 50,
) -> Dict[str, Any]:
    """Get distribution of a trait for filtered molecules."""
    if trait not in TRAIT_COLUMNS:
        return {"error": f"Invalid trait: {trait}"}

    needed_cols = ["SMILES"] + TRAIT_COLUMNS
    df = _load_parquet_for_batches(batch_codes, columns=needed_cols)
    if df.empty:
        return {"error": "No data found"}

    # Apply conditions
    trait_conds = conditions.get("traits", {})
    for tk, cond in trait_conds.items():
        if tk not in TRAIT_COLUMNS:
            continue
        df[tk] = pd.to_numeric(df[tk], errors="coerce")
        if "min" in cond and cond["min"] is not None:
            df = df[df[tk] >= cond["min"]]
        if "max" in cond and cond["max"] is not None:
            df = df[df[tk] <= cond["max"]]
        if "values" in cond and cond["values"]:
            df = df[df[tk].isin(cond["values"])]

    # Apply prediction conditions
    pred_conds = conditions.get("predictions", {})
    if pred_conds:
        from Database.Tools.Dry.Dry_Prediction import filter_by_predictions
        pred_smiles = filter_by_predictions(batch_codes, pred_conds)
        if pred_smiles is not None:
            df = df[df["SMILES"].isin(pred_smiles)]

    df = df.dropna(subset=[trait])
    df[trait] = pd.to_numeric(df[trait], errors="coerce")
    df = df.dropna(subset=[trait])

    if len(df) == 0:
        return {
            "trait": trait,
            "trait_label": TRAIT_LABELS.get(trait, trait),
            "trait_type": TRAIT_TYPES.get(trait, "continuous"),
            "total_count": 0,
            "bins": [],
        }

    values = df[trait].values
    trait_type = TRAIT_TYPES.get(trait, "continuous")
    min_val = float(np.min(values))
    max_val = float(np.max(values))

    if trait_type == "integer":
        int_min = int(np.floor(min_val))
        int_max = int(np.ceil(max_val))
        hist_bins = []
        for iv in range(int_min, int_max + 1):
            mask = (values >= iv - 0.5) & (values < iv + 0.5)
            hist_bins.append({
                "min": iv, "max": iv,
                "count": int(np.sum(mask)),
            })
    elif max_val == min_val:
        hist_bins = [{"min": min_val, "max": max_val, "count": len(values)}]
    else:
        bin_edges = np.linspace(min_val, max_val, bins + 1)
        hist_bins = []
        for i in range(len(bin_edges) - 1):
            bmin = float(bin_edges[i])
            bmax = float(bin_edges[i + 1])
            if i == len(bin_edges) - 2:
                mask = (values >= bmin) & (values <= bmax)
            else:
                mask = (values >= bmin) & (values < bmax)
            hist_bins.append({
                "min": round(bmin, 4),
                "max": round(bmax, 4),
                "count": int(np.sum(mask)),
            })

    # Peak / tick
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
        "total_count": len(df),
        "min_value": round(min_val, 4),
        "max_value": round(max_val, 4),
        "mean_value": round(float(np.mean(values)), 4),
        "std_value": round(float(np.std(values)), 4),
        "peak_center": round(peak_center, 4),
        "tick_interval": tick_interval,
        "bins": hist_bins,
    }


def get_filtered_molecules_by_range(
    batch_codes: List[str],
    conditions: Dict[str, Any],
    trait: str,
    min_value: float,
    max_value: float,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get molecules in a trait range from the filtered set."""
    if trait not in TRAIT_COLUMNS:
        return {"error": f"Invalid trait: {trait}"}

    needed_cols = ["SMILES"] + TRAIT_COLUMNS
    df = _load_parquet_for_batches(batch_codes, columns=needed_cols)
    if df.empty:
        return {"error": "No data found"}

    # Apply conditions
    trait_conds = conditions.get("traits", {})
    for tk, cond in trait_conds.items():
        if tk not in TRAIT_COLUMNS:
            continue
        df[tk] = pd.to_numeric(df[tk], errors="coerce")
        if "min" in cond and cond["min"] is not None:
            df = df[df[tk] >= cond["min"]]
        if "max" in cond and cond["max"] is not None:
            df = df[df[tk] <= cond["max"]]
        if "values" in cond and cond["values"]:
            df = df[df[tk].isin(cond["values"])]

    # Apply prediction conditions
    pred_conds = conditions.get("predictions", {})
    if pred_conds:
        from Database.Tools.Dry.Dry_Prediction import filter_by_predictions
        pred_smiles = filter_by_predictions(batch_codes, pred_conds)
        if pred_smiles is not None:
            df = df[df["SMILES"].isin(pred_smiles)]

    df = df.dropna(subset=[trait])
    df[trait] = pd.to_numeric(df[trait], errors="coerce")
    df = df.dropna(subset=[trait])
    df = df[(df[trait] >= min_value) & (df[trait] <= max_value)]

    total_in_range = len(df)
    if limit and limit > 0:
        df = df.head(limit)

    # Resolve LabIDs
    smiles_list = df["SMILES"].tolist()
    lab_id_map: Dict[str, str] = {}
    if smiles_list:
        conn = _get_connection()
        try:
            placeholders = ",".join(["?"] * len(smiles_list))
            rows = conn.execute(
                f"SELECT SMILES, LabID FROM Info WHERE SMILES IN ({placeholders})",
                smiles_list,
            ).fetchall()
            for r in rows:
                lab_id_map[r["SMILES"]] = r["LabID"]
        finally:
            conn.close()

    molecules = []
    for _, row in df.iterrows():
        sm = str(row["SMILES"])
        molecules.append({
            "lab_id": lab_id_map.get(sm, "Unknown"),
            "smiles": sm,
            "value": round(float(row[trait]), 4),
        })

    return {
        "total_in_range": total_in_range,
        "returned_count": len(molecules),
        "molecules": molecules,
    }


def package_filtered_results(
    batch_codes: List[str],
    conditions: Dict[str, Any],
) -> io.BytesIO:
    """Export filtered molecules as a zip containing a parquet file."""
    needed_cols = ["SMILES"] + TRAIT_COLUMNS
    df = _load_parquet_for_batches(batch_codes, columns=needed_cols)

    if not df.empty:
        trait_conds = conditions.get("traits", {})
        for tk, cond in trait_conds.items():
            if tk not in TRAIT_COLUMNS:
                continue
            df[tk] = pd.to_numeric(df[tk], errors="coerce")
            if "min" in cond and cond["min"] is not None:
                df = df[df[tk] >= cond["min"]]
            if "max" in cond and cond["max"] is not None:
                df = df[df[tk] <= cond["max"]]
            if "values" in cond and cond["values"]:
                df = df[df[tk].isin(cond["values"])]

        # Apply prediction conditions
        pred_conds = conditions.get("predictions", {})
        if pred_conds:
            from Database.Tools.Dry.Dry_Prediction import filter_by_predictions
            pred_smiles = filter_by_predictions(batch_codes, pred_conds)
            if pred_smiles is not None:
                df = df[df["SMILES"].isin(pred_smiles)]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        parquet_buf = io.BytesIO()
        df.to_parquet(parquet_buf, index=False)
        zf.writestr("filtered_molecules.parquet", parquet_buf.getvalue())

    buf.seek(0)
    return buf
