"""Dry preparation pipeline (v2).

New architecture — validate + import (no generation steps).

Pipeline phases:
Phase A — Discover & Validate:
  Scan Separate/*.parquet for batch files.
  Validate each file has a SMILES column with non-empty data.
  Optionally validate SMILES alignment with Property/*.parquet.

Phase B — Dedup & Assign IDs:
  Load all SMILES from new Separate files.
  Cross-reference existing Info table in Dry.db.
  For new SMILES: assign next LabID (L00000001, L00000002, ...).
  For each molecule-in-batch: assign BatchID (e.g. BatchE0010000001).

Phase C — Write to Dry.db:
  Insert Info rows (LabID, BatchID, SMILES).
  Update _Batches metadata table.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import pyarrow.parquet as pq

# ═══════════════════════════════════════════════════════════════════
#  全局路径配置 — 修改这两行即可切换数据源
# ═══════════════════════════════════════════════════════════════════
DRY_DATA_ROOT = Path(r"E:\ExperimentData\DryData")
DRY_DB_PATH   = Path(__file__).resolve().parent / "Dry.db"
# ═══════════════════════════════════════════════════════════════════

try:
    from ..Tools.Dry.Dry_Db_Maker import (
        DEFAULT_DRY_DB_PATH,
        make_dry_database,
        get_existing_lab_ids,
        get_existing_batch_codes,
        get_next_lab_id_number,
    )
except ImportError:  # pragma: no cover
    import sys
    _tools_dry = str(Path(__file__).resolve().parents[1] / "Tools" / "Dry")
    if _tools_dry not in sys.path:
        sys.path.insert(0, _tools_dry)
    from Dry_Db_Maker import (
        DEFAULT_DRY_DB_PATH,
        make_dry_database,
        get_existing_lab_ids,
        get_existing_batch_codes,
        get_next_lab_id_number,
    )

import datetime

BATCH_FILE_PATTERN = re.compile(r"^(Batch([EG])(\d{3}))$")


def _utc_now_text() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _format_lab_id(num: int) -> str:
    """Format LabID as L00000001."""
    return f"L{num:08d}"


def _format_batch_id(batch_code: str, seq: int) -> str:
    """Format BatchID as e.g. BatchE0010000001."""
    return f"{batch_code}{seq:07d}"


# ─────────────────────────────────────────────────
#  Phase A: Discover & Validate
# ─────────────────────────────────────────────────

def _discover_separate_files(separate_dir: Path) -> List[Dict[str, Any]]:
    """Discover Separate/*.parquet batch files."""
    if not separate_dir.exists() or not separate_dir.is_dir():
        return []

    items: List[Dict[str, Any]] = []
    for f in sorted(separate_dir.glob("Batch*.parquet")):
        match = BATCH_FILE_PATTERN.match(f.stem)
        if not match:
            continue
        batch_code = match.group(1)
        source_type = "External" if match.group(2) == "E" else "Generated"
        items.append({
            "batch_code": batch_code,
            "source_type": source_type,
            "separate_file": f,
        })
    return items


def _validate_separate_file(separate_file: Path) -> Dict[str, Any]:
    """Validate that a Separate parquet has a SMILES column with data."""
    try:
        pf = pq.ParquetFile(str(separate_file))
        schema_names = [str(f.name) for f in pf.schema_arrow]
        if "SMILES" not in schema_names:
            return {"valid": False, "message": "Missing SMILES column.", "row_count": 0}
        row_count = pf.metadata.num_rows
        if row_count == 0:
            return {"valid": False, "message": "File has 0 rows.", "row_count": 0}
        return {"valid": True, "message": f"{row_count} rows.", "row_count": row_count}
    except Exception as exc:
        return {"valid": False, "message": f"Read error: {exc}", "row_count": 0}


def _validate_smiles_alignment(
    separate_file: Path,
    property_file: Path,
) -> Dict[str, Any]:
    """Verify Property parquet SMILES match Separate parquet row-by-row."""
    try:
        sep_pf = pq.ParquetFile(str(separate_file))
        prop_pf = pq.ParquetFile(str(property_file))
        sep_rows = sep_pf.metadata.num_rows
        prop_rows = prop_pf.metadata.num_rows

        if sep_rows != prop_rows:
            return {
                "valid": False,
                "message": (
                    f"Row count mismatch: Separate={sep_rows}, Property={prop_rows}."
                ),
            }

        CHUNK = 50_000
        sep_iter = sep_pf.iter_batches(columns=["SMILES"], batch_size=CHUNK)
        prop_iter = prop_pf.iter_batches(columns=["SMILES"], batch_size=CHUNK)
        checked = 0

        for sep_batch, prop_batch in zip(sep_iter, prop_iter):
            sep_smiles = sep_batch.column(0).to_pylist()
            prop_smiles = prop_batch.column(0).to_pylist()

            for i, (s, p) in enumerate(zip(sep_smiles, prop_smiles)):
                s_val = str(s).strip() if s is not None else ""
                p_val = str(p).strip() if p is not None else ""
                if s_val != p_val:
                    row_idx = checked + i
                    return {
                        "valid": False,
                        "message": (
                            f"SMILES mismatch at row {row_idx}: "
                            f"Separate='{s_val[:60]}' vs Property='{p_val[:60]}'."
                        ),
                    }
            checked += len(sep_smiles)

        return {"valid": True, "message": f"All {sep_rows} SMILES match."}
    except Exception as exc:
        return {"valid": False, "message": f"Validation error: {exc}"}


# ─────────────────────────────────────────────────
#  Phase B: Dedup & Assign IDs
# ─────────────────────────────────────────────────

def _load_smiles_from_parquet(separate_file: Path) -> List[str]:
    """Read SMILES column from a Separate parquet, preserving order."""
    CHUNK = 100_000
    pf = pq.ParquetFile(str(separate_file))
    result: List[str] = []
    for batch in pf.iter_batches(columns=["SMILES"], batch_size=CHUNK):
        for val in batch.column(0).to_pylist():
            s = str(val).strip() if val is not None else ""
            if s:
                result.append(s)
    return result


def _assign_ids_for_batch(
    batch_code: str,
    smiles_list: List[str],
    existing_smiles_to_lab: Dict[str, str],
    next_lab_num: int,
) -> tuple[List[tuple[str, str, str]], int]:
    """Assign LabID and BatchID for each SMILES in a batch.

    Returns:
        (rows, updated_next_lab_num)
        rows: list of (LabID, BatchID, SMILES) tuples
    """
    rows: List[tuple[str, str, str]] = []
    batch_seq = 1

    for smiles in smiles_list:
        # Reuse existing LabID or assign a new one
        lab_id = existing_smiles_to_lab.get(smiles)
        if lab_id is None:
            lab_id = _format_lab_id(next_lab_num)
            existing_smiles_to_lab[smiles] = lab_id
            next_lab_num += 1

        batch_id = _format_batch_id(batch_code, batch_seq)
        rows.append((lab_id, batch_id, smiles))
        batch_seq += 1

    return rows, next_lab_num


# ─────────────────────────────────────────────────
#  Phase C: Write to Dry.db
# ─────────────────────────────────────────────────

def _write_info_to_db(
    db_path: str,
    batch_code: str,
    source_type: str,
    rows: List[tuple[str, str, str]],
) -> Dict[str, Any]:
    """Insert Info rows and update _Batches for one batch."""
    now = _utc_now_text()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Remove old rows for this batch (re-import scenario)
        conn.execute(
            "DELETE FROM Info WHERE BatchID LIKE ?",
            (f"{batch_code}%",),
        )

        # Batch insert
        conn.executemany(
            "INSERT INTO Info (LabID, BatchID, SMILES) VALUES (?, ?, ?)",
            rows,
        )

        # Upsert _Batches
        conn.execute(
            """
            INSERT INTO _Batches (batch_code, source_type, molecule_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(batch_code) DO UPDATE SET
                source_type = excluded.source_type,
                molecule_count = excluded.molecule_count,
                updated_at = excluded.updated_at
            """,
            (batch_code, source_type, len(rows), now, now),
        )

        conn.commit()
        return {
            "status": "success",
            "batch_code": batch_code,
            "rows_written": len(rows),
        }
    except Exception as exc:
        conn.rollback()
        return {
            "status": "error",
            "batch_code": batch_code,
            "message": str(exc),
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────────
#  run — single batch (Phase A only, quick test)
# ─────────────────────────────────────────────────

def run(
    separate_file_path: str,
    db_path: str | None = None,
) -> Dict[str, Any]:
    """Run pipeline for a single Separate parquet file."""
    separate_file = Path(separate_file_path)
    if not separate_file.exists():
        return {"status": "error", "messages": [f"File not found: {separate_file_path}"]}

    match = BATCH_FILE_PATTERN.match(separate_file.stem)
    if not match:
        return {"status": "error", "messages": ["File name must match Batch[E|G]NNN.parquet"]}

    batch_code = match.group(1)
    source_type = "External" if match.group(2) == "E" else "Generated"

    # Phase A: validate
    validation = _validate_separate_file(separate_file)
    if not validation["valid"]:
        return {"status": "error", "messages": [validation["message"]]}

    # Phase B: load + assign
    if db_path is None:
        db_path_str = str(DRY_DB_PATH)
    else:
        db_path_str = str(db_path)

    make_dry_database(db_path_str)
    existing_map = get_existing_lab_ids(db_path_str)
    next_num = get_next_lab_id_number(db_path_str)

    smiles_list = _load_smiles_from_parquet(separate_file)
    rows, _ = _assign_ids_for_batch(batch_code, smiles_list, existing_map, next_num)

    # Phase C: write
    result = _write_info_to_db(db_path_str, batch_code, source_type, rows)
    return result


# ─────────────────────────────────────────────────
#  run_refresh — master entry point (Phase A+B+C)
# ─────────────────────────────────────────────────

def run_refresh(
    dry_root: str | Path | None = None,
    separate_dir: str | Path | None = None,
    property_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    note: str | None = None,
    progress_callback: Callable | None = None,
) -> Dict[str, Any]:
    """Refresh Dry data: discover new Separate files and sync into Dry.db.

    Phase A — Discover & Validate all Separate/*.parquet files.
    Phase B — Dedup across batches, assign LabID / BatchID.
    Phase C — Write Info table and _Batches metadata to Dry.db.
    """
    start_time = time.time()

    # ── resolve paths ──
    dry_root_path = (
        Path(dry_root) if dry_root is not None
        else DRY_DATA_ROOT
    )
    if not dry_root_path.exists() or not dry_root_path.is_dir():
        return {
            "status": "error",
            "message": f"DRY_DATA_ROOT not found: {dry_root_path}",
            "http_status": 400,
        }

    separate_dir_path = (
        Path(separate_dir) if separate_dir is not None
        else Path(os.getenv("DRY_SEPARATE_DIR", str(dry_root_path / "Separate")))
    )
    property_dir_path = (
        Path(property_dir) if property_dir is not None
        else Path(os.getenv("DRY_PROPERTY_DIR", str(dry_root_path / "Property")))
    )

    if db_path is None:
        db_path_str = str(DRY_DB_PATH)
    else:
        db_path_str = str(db_path)

    try:
        # Ensure DB exists
        make_dry_database(db_path_str)

        # ═══════════════════════════════════════════
        #  Phase A — Discover & Validate
        # ═══════════════════════════════════════════
        if progress_callback is not None:
            progress_callback("phase_a", "", "discover", "started", None)

        discovered = _discover_separate_files(separate_dir_path)
        existing_batch_codes = get_existing_batch_codes(db_path_str)

        # Only process new batches not already in DB
        new_batches = [
            item for item in discovered
            if item["batch_code"] not in existing_batch_codes
        ]

        validation_results: List[Dict[str, Any]] = []
        valid_batches: List[Dict[str, Any]] = []

        for item in new_batches:
            batch_code = item["batch_code"]
            if progress_callback is not None:
                progress_callback("phase_a", batch_code, "validate", "started", None)

            val = _validate_separate_file(item["separate_file"])
            val["batch_code"] = batch_code
            validation_results.append(val)

            if not val["valid"]:
                continue

            # Optional: validate alignment with Property file
            prop_file = property_dir_path / f"{batch_code}.parquet"
            if prop_file.exists():
                alignment = _validate_smiles_alignment(item["separate_file"], prop_file)
                val["property_alignment"] = alignment
                if not alignment["valid"]:
                    val["property_warning"] = alignment["message"]

            valid_batches.append(item)

        # ═══════════════════════════════════════════
        #  Phase B — Dedup & Assign IDs
        # ═══════════════════════════════════════════
        if progress_callback is not None:
            progress_callback("phase_b", "", "dedup", "started", None)

        existing_map = get_existing_lab_ids(db_path_str)
        next_num = get_next_lab_id_number(db_path_str)

        batch_rows: Dict[str, List[tuple[str, str, str]]] = {}
        batch_meta: Dict[str, str] = {}  # batch_code -> source_type

        for item in valid_batches:
            batch_code = item["batch_code"]
            if progress_callback is not None:
                progress_callback("phase_b", batch_code, "assign_ids", "started", None)

            smiles_list = _load_smiles_from_parquet(item["separate_file"])
            rows, next_num = _assign_ids_for_batch(
                batch_code, smiles_list, existing_map, next_num,
            )
            batch_rows[batch_code] = rows
            batch_meta[batch_code] = item["source_type"]

        # ═══════════════════════════════════════════
        #  Phase C — Write to Dry.db
        # ═══════════════════════════════════════════
        if progress_callback is not None:
            progress_callback("phase_c", "", "write_db", "started", None)

        write_results: List[Dict[str, Any]] = []
        for batch_code, rows in batch_rows.items():
            if progress_callback is not None:
                progress_callback("phase_c", batch_code, "write", "started", None)

            wr = _write_info_to_db(
                db_path_str, batch_code, batch_meta[batch_code], rows,
            )
            write_results.append(wr)

        ok = sum(1 for r in write_results if r.get("status") == "success")
        fail = sum(1 for r in write_results if r.get("status") == "error")

        overall_status = "success" if fail == 0 else "warning"

        return {
            "status": overall_status,
            "elapsed_seconds": round(time.time() - start_time, 3),
            "dry_root": str(dry_root_path),
            "separate_dir": str(separate_dir_path),
            "property_dir": str(property_dir_path),
            "db_path": db_path_str,
            "scanned_batches": len(discovered),
            "already_registered": len(existing_batch_codes),
            "new_batches_found": len(new_batches),
            "validation": validation_results,
            "phase_c": {
                "batches_written": ok,
                "batches_failed": fail,
                "results": write_results,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "http_status": 500,
        }


if __name__ == "__main__":
    # Single batch test
    result = run(r"E:\DryData\Separate\BatchE001.parquet")
    print(json.dumps(result, ensure_ascii=False, indent=2))
