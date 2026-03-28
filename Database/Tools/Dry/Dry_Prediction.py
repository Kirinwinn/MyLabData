"""Prediction data management for Proby and Tox21.

Provides:
  - Solvent mapping from Supporting/Solvent.md
  - Availability scanning for Refresh
  - Query functions for View / Compare / Search modes

Architecture:
  Normalized : E:\\DryData\\Prediction\\{Model}\\{BatchCode}.parquet
  (Normalization is done externally via Prediction_Normalize.ipynb)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

# ── paths ──

try:
    from Database.Dry import DRY_DATA_ROOT
except ImportError:
    DRY_DATA_ROOT = Path(os.getenv("DRY_DATA_ROOT", r"E:\DryData"))

PREDICTION_DIR = DRY_DATA_ROOT / "Prediction"
SUPPORTING_DIR = Path(__file__).resolve().parents[3] / "Supporting"

# ── model definitions ──

ACTIVE_MODELS = ["Proby", "Tox21"]

PROBY_RESULT_COLUMNS = [
    "abs", "emi", "plqy", "e", "log10e", "lifetime",
    "abs_fwhm_cm", "emi_fwhm_cm", "abs_fwhm_nm", "emi_fwhm_nm",
]

PROBY_RESULT_LABELS: Dict[str, str] = {
    "abs": "Absorption λmax",
    "emi": "Emission λmax",
    "plqy": "PLQY",
    "e": "ε",
    "log10e": "log₁₀ε",
    "lifetime": "Lifetime",
    "abs_fwhm_cm": "Abs FWHM (cm⁻¹)",
    "emi_fwhm_cm": "Emi FWHM (cm⁻¹)",
    "abs_fwhm_nm": "Abs FWHM (nm)",
    "emi_fwhm_nm": "Emi FWHM (nm)",
}

TOX21_RESULT_COLUMNS = [
    "NR-AR", "NR-AR-LBD", "NR-AhR", "NR-Aromatase",
    "NR-ER", "NR-ER-LBD", "NR-PPAR-gamma",
    "SR-ARE", "SR-ATAD5", "SR-HSE", "SR-MMP", "SR-p53",
]

TOX21_RESULT_LABELS: Dict[str, str] = {c: c for c in TOX21_RESULT_COLUMNS}

# ── solvent mapping ──

_solvent_cache: Optional[Dict[str, str]] = None


def load_solvent_map() -> Dict[str, str]:
    """Load SMILES → abbreviation mapping from Supporting/Solvent.md.

    Returns dict like {"CS(C)=O": "DMSO", "ClCCl": "DCM", ...}
    """
    global _solvent_cache
    if _solvent_cache is not None:
        return _solvent_cache

    md_path = SUPPORTING_DIR / "Solvent.md"
    mapping: Dict[str, str] = {}
    if md_path.exists():
        for line in md_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*`([^`]+)`\s*\|\s*\*\*([^*]+)\*\*\s*\|", line)
            if m:
                mapping[m.group(1)] = m.group(2)
    _solvent_cache = mapping
    return mapping


def solvent_display_name(solvent_smiles: str) -> str:
    """Return human-readable abbreviation for a solvent SMILES."""
    m = load_solvent_map()
    return m.get(solvent_smiles, solvent_smiles)


# ── sheet name parsing ──

def _parse_sheet_solvent(sheet_name: str) -> str:
    """Extract solvent SMILES from a Proby sheet name like 'CS(C)=O (8)'."""
    m = re.match(r"^(.+?)\s*\(\d+\)$", sheet_name)
    return m.group(1) if m else sheet_name


# ── availability detection ──

def get_prediction_availability(batch_code: str) -> Dict[str, bool]:
    """Check which models have *normalized* data for a batch."""
    result: Dict[str, bool] = {}
    for model in ACTIVE_MODELS:
        pq_path = PREDICTION_DIR / model / f"{batch_code}.parquet"
        result[model] = pq_path.exists()
    return result


def get_available_solvents(batch_code: str) -> List[Dict[str, str]]:
    """List available solvents for Proby from normalized data."""
    pq_path = PREDICTION_DIR / "Proby" / f"{batch_code}.parquet"
    if not pq_path.exists():
        return []
    try:
        df = pd.read_parquet(pq_path, columns=["Solvent"])
        solvents = sorted(df["Solvent"].dropna().unique())
        sol_map = load_solvent_map()
        return [{"smiles": s, "label": sol_map.get(s, s)} for s in solvents]
    except Exception:
        return []


def get_model_result_info(model: str) -> Dict[str, Any]:
    """Return result column definitions for a model."""
    if model == "Proby":
        return {
            "columns": PROBY_RESULT_COLUMNS,
            "labels": PROBY_RESULT_LABELS,
            "has_solvent": True,
        }
    elif model == "Tox21":
        return {
            "columns": TOX21_RESULT_COLUMNS,
            "labels": TOX21_RESULT_LABELS,
            "has_solvent": False,
        }
    return {"columns": [], "labels": {}, "has_solvent": False}


# ═══════════════════════════════════════════════════════════════════
#  SCAN: for Refresh
# ═══════════════════════════════════════════════════════════════════

def scan_all_prediction_availability(
    progress_callback=None,
) -> Dict[str, Any]:
    """Scan Prediction/{Model}/ for all available prediction parquet files.

    Returns summary like:
        {"Proby": {"batches": ["BatchG001", ...], "count": 4},
         "Tox21": {"batches": [...], "count": 6}}
    """
    result: Dict[str, Any] = {}
    for model in ACTIVE_MODELS:
        model_dir = PREDICTION_DIR / model
        if progress_callback:
            progress_callback("phase_pred", model, "scan", "started", None)
        batches: List[str] = []
        if model_dir.exists():
            for pq in sorted(model_dir.glob("*.parquet")):
                batches.append(pq.stem)
        result[model] = {"batches": batches, "count": len(batches)}
        if progress_callback:
            detail = f"{len(batches)} batch(es)"
            progress_callback("phase_pred", model, "scan", "done", detail)
    return result


# ═══════════════════════════════════════════════════════════════════
#  QUERY: helpers
# ═══════════════════════════════════════════════════════════════════

def _load_normalized(model: str, batch_code: str) -> Optional[pd.DataFrame]:
    """Load normalized parquet for a model+batch. Returns None if missing."""
    pq_path = PREDICTION_DIR / model / f"{batch_code}.parquet"
    if not pq_path.exists():
        return None
    try:
        return pd.read_parquet(pq_path)
    except Exception:
        return None


def _load_normalized_multi(model: str, batch_codes: List[str]) -> pd.DataFrame:
    """Load and concatenate normalized parquet for multiple batches."""
    frames = []
    for bc in batch_codes:
        df = _load_normalized(model, bc)
        if df is not None:
            df["_batch"] = bc
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════
#  QUERY: ViewMode
# ═══════════════════════════════════════════════════════════════════

def get_prediction_for_molecule(
    batch_code: str, smiles: str, model: str, solvent: Optional[str] = None,
) -> Dict[str, Any]:
    """Get prediction results for a single molecule in a batch."""
    df = _load_normalized(model, batch_code)
    if df is None:
        return {"available": False}

    mask = df["SMILES"] == smiles
    if model == "Proby" and solvent:
        mask = mask & (df["Solvent"] == solvent)

    rows = df[mask]
    if rows.empty:
        return {"available": True, "found": False, "values": {}}

    cols = PROBY_RESULT_COLUMNS if model == "Proby" else TOX21_RESULT_COLUMNS
    record = rows.iloc[0]
    values = {}
    for c in cols:
        if c in record.index:
            v = record[c]
            values[c] = round(float(v), 4) if pd.notna(v) else None
        else:
            values[c] = None

    return {"available": True, "found": True, "values": values}


def get_prediction_distribution(
    batch_code: str,
    model: str,
    metric: str,
    solvent: Optional[str] = None,
    bins: int = 50,
) -> Dict[str, Any]:
    """Distribution of a prediction metric for chart display."""
    df = _load_normalized(model, batch_code)
    if df is None:
        return {"error": "No normalized data"}

    if model == "Proby" and solvent:
        df = df[df["Solvent"] == solvent]

    if metric not in df.columns:
        return {"error": f"Metric '{metric}' not found"}

    labels = PROBY_RESULT_LABELS if model == "Proby" else TOX21_RESULT_LABELS

    df = df.dropna(subset=[metric])
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df = df.dropna(subset=[metric])

    if df.empty:
        return {
            "metric": metric,
            "metric_label": labels.get(metric, metric),
            "total_count": 0,
            "bins": [],
        }

    values = df[metric].values
    min_val = float(np.min(values))
    max_val = float(np.max(values))

    if max_val == min_val:
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

    peak_bin = max(hist_bins, key=lambda b: b["count"]) if hist_bins else None
    peak_center = (peak_bin["min"] + peak_bin["max"]) / 2 if peak_bin else 0
    tick_interval = (
        round(abs(peak_center) * 0.1, 4)
        if peak_center != 0
        else round((max_val - min_val) / 10, 4)
    )

    return {
        "metric": metric,
        "metric_label": labels.get(metric, metric),
        "total_count": len(values),
        "min_value": round(min_val, 4),
        "max_value": round(max_val, 4),
        "mean_value": round(float(np.mean(values)), 4),
        "std_value": round(float(np.std(values)), 4),
        "peak_center": round(peak_center, 4),
        "tick_interval": tick_interval,
        "bins": hist_bins,
    }


def get_prediction_molecules_by_range(
    batch_code: str,
    model: str,
    metric: str,
    min_value: float,
    max_value: float,
    solvent: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Get molecules in a prediction metric range."""
    import sqlite3

    try:
        from Database.Dry import DRY_DB_PATH
    except ImportError:
        DRY_DB_PATH = Path(os.getenv("DRY_DB_PATH",
            str(Path(__file__).resolve().parents[2] / "Dry" / "Dry.db")))

    df = _load_normalized(model, batch_code)
    if df is None:
        return {"error": "No normalized data"}

    if model == "Proby" and solvent:
        df = df[df["Solvent"] == solvent]

    if metric not in df.columns:
        return {"error": f"Metric '{metric}' not found"}

    df = df.dropna(subset=[metric])
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df = df.dropna(subset=[metric])
    df = df[(df[metric] >= min_value) & (df[metric] <= max_value)]

    total_in_range = len(df)
    if limit and limit > 0:
        df = df.head(limit)

    smiles_list = df["SMILES"].tolist()
    lab_id_map: Dict[str, str] = {}
    if smiles_list:
        conn = sqlite3.connect(str(DRY_DB_PATH))
        conn.row_factory = sqlite3.Row
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
            "value": round(float(row[metric]), 4),
        })

    return {
        "total_in_range": total_in_range,
        "returned_count": len(molecules),
        "molecules": molecules,
    }


# ═══════════════════════════════════════════════════════════════════
#  QUERY: CompareMode
# ═══════════════════════════════════════════════════════════════════

def get_molecule_predictions(
    smiles: str, batch_codes: List[str],
) -> Dict[str, Any]:
    """Get all available prediction data for a molecule across batches.

    Returns:
        {
            "Proby": {"available": True, "solvents": [...], "data": {solvent: {metric: val}}},
            "Tox21": {"available": True, "data": {metric: val}},
        }
    """
    result: Dict[str, Any] = {}

    for model in ACTIVE_MODELS:
        df = _load_normalized_multi(model, batch_codes)
        if df.empty:
            result[model] = {"available": False}
            continue

        mol_df = df[df["SMILES"] == smiles]
        if mol_df.empty:
            result[model] = {"available": True, "found": False}
            continue

        if model == "Proby":
            sol_map = load_solvent_map()
            solvents = sorted(mol_df["Solvent"].dropna().unique())
            solvent_data = {}
            for sol in solvents:
                sol_rows = mol_df[mol_df["Solvent"] == sol]
                if sol_rows.empty:
                    continue
                rec = sol_rows.iloc[0]
                vals = {}
                for c in PROBY_RESULT_COLUMNS:
                    v = rec.get(c)
                    vals[c] = round(float(v), 4) if pd.notna(v) else None
                solvent_data[sol] = vals
            result[model] = {
                "available": True,
                "found": True,
                "solvents": [
                    {"smiles": s, "label": sol_map.get(s, s)} for s in solvents
                ],
                "data": solvent_data,
            }
        elif model == "Tox21":
            rec = mol_df.iloc[0]
            vals = {}
            for c in TOX21_RESULT_COLUMNS:
                v = rec.get(c)
                vals[c] = round(float(v), 4) if pd.notna(v) else None
            result[model] = {
                "available": True,
                "found": True,
                "data": vals,
            }

    return result


# ═══════════════════════════════════════════════════════════════════
#  QUERY: SearchMode
# ═══════════════════════════════════════════════════════════════════

def filter_by_predictions(
    batch_codes: List[str],
    pred_conditions: Dict[str, Any],
) -> Optional[Set[str]]:
    """Return set of SMILES matching ALL prediction conditions (intersection).

    pred_conditions example:
        {
            "Proby": {
                "solvent": "CS(C)=O",
                "metrics": {"abs": {"min": 300, "max": 500}}
            },
            "Tox21": {
                "metrics": {"NR-AR": {"min": 0.1, "max": 0.5}}
            }
        }

    Returns None if no prediction conditions are set (meaning: no restriction).
    Returns a set of SMILES if conditions exist.
    """
    if not pred_conditions:
        return None

    smiles_sets: list[set[str]] = []

    for model, mcond in pred_conditions.items():
        if model not in ACTIVE_MODELS:
            continue
        metrics = mcond.get("metrics", {})
        if not metrics:
            continue

        df = _load_normalized_multi(model, batch_codes)
        if df.empty:
            return set()  # model required but no data → empty

        if model == "Proby":
            solvent = mcond.get("solvent")
            if solvent:
                df = df[df["Solvent"] == solvent]

        for metric_key, cond in metrics.items():
            if metric_key not in df.columns:
                continue
            df[metric_key] = pd.to_numeric(df[metric_key], errors="coerce")
            if "min" in cond and cond["min"] is not None:
                df = df[df[metric_key] >= cond["min"]]
            if "max" in cond and cond["max"] is not None:
                df = df[df[metric_key] <= cond["max"]]

        smiles_sets.append(set(df["SMILES"].dropna().unique()))

    if not smiles_sets:
        return None

    return set.intersection(*smiles_sets)


def get_prediction_filtered_distribution(
    batch_codes: List[str],
    pred_conditions: Dict[str, Any],
    model: str,
    metric: str,
    solvent: Optional[str] = None,
    allowed_smiles: Optional[Set[str]] = None,
    bins: int = 50,
) -> Dict[str, Any]:
    """Distribution of a prediction metric within a filtered set."""
    df = _load_normalized_multi(model, batch_codes)
    if df.empty:
        return {"error": "No data"}

    if model == "Proby" and solvent:
        df = df[df["Solvent"] == solvent]

    if allowed_smiles is not None:
        df = df[df["SMILES"].isin(allowed_smiles)]

    if metric not in df.columns:
        return {"error": f"Metric '{metric}' not found"}

    labels = PROBY_RESULT_LABELS if model == "Proby" else TOX21_RESULT_LABELS

    df = df.dropna(subset=[metric])
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df = df.dropna(subset=[metric])

    if df.empty:
        return {
            "metric": metric,
            "metric_label": labels.get(metric, metric),
            "total_count": 0,
            "bins": [],
        }

    values = df[metric].values
    min_val = float(np.min(values))
    max_val = float(np.max(values))

    if max_val == min_val:
        hist_bins = [{"min": min_val, "max": max_val, "count": len(values)}]
    else:
        bin_edges = np.linspace(min_val, max_val, bins + 1)
        hist_bins = []
        for i in range(len(bin_edges) - 1):
            bmin = float(bin_edges[i])
            bmax = float(bin_edges[i + 1])
            mask = (
                (values >= bmin) & (values <= bmax)
                if i == len(bin_edges) - 2
                else (values >= bmin) & (values < bmax)
            )
            hist_bins.append({
                "min": round(bmin, 4),
                "max": round(bmax, 4),
                "count": int(np.sum(mask)),
            })

    peak_bin = max(hist_bins, key=lambda b: b["count"]) if hist_bins else None
    peak_center = (peak_bin["min"] + peak_bin["max"]) / 2 if peak_bin else 0
    tick_interval = (
        round(abs(peak_center) * 0.1, 4)
        if peak_center != 0
        else round((max_val - min_val) / 10, 4)
    )

    return {
        "metric": metric,
        "metric_label": labels.get(metric, metric),
        "total_count": len(values),
        "min_value": round(min_val, 4),
        "max_value": round(max_val, 4),
        "mean_value": round(float(np.mean(values)), 4),
        "std_value": round(float(np.std(values)), 4),
        "peak_center": round(peak_center, 4),
        "tick_interval": tick_interval,
        "bins": hist_bins,
    }
