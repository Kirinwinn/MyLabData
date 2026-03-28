"""Dry database maker.

This module is dedicated to DryData indexing and must not affect Wet db logic.

New architecture (v2):
  - Info table:     (LabID, BatchID, SMILES) — one row per molecule-batch pair
  - _Batches table: auxiliary batch metadata

Trait / Property data stays in Parquet files (hybrid approach for 30M+ scale).
Prediction data is per-model, handled separately in the future.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path


# Default fallback — the authoritative path lives in Database.Dry.Dry_Pipeline
DEFAULT_DRY_DB_PATH = Path(os.getenv("DRY_DB_PATH",
    str(Path(__file__).resolve().parents[2] / "Dry" / "Dry.db")))


def _utc_now_text() -> str:
    """Return current UTC timestamp text for DB defaults."""
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _init_dry_schema(conn: sqlite3.Connection) -> None:
    """Create Dry core tables and indexes (v2 schema)."""
    cursor = conn.cursor()

    # ── Info table: the single source of truth for molecule registration ──
    # One row per (LabID, BatchID) pair.
    # If a SMILES appears in 3 batches, it has 3 rows sharing the same LabID.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS Info
        (
            LabID   TEXT NOT NULL,
            BatchID TEXT NOT NULL,
            SMILES  TEXT NOT NULL,
            PRIMARY KEY (LabID, BatchID)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_info_smiles ON Info(SMILES)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_info_batch  ON Info(BatchID)")

    # ── _Batches: lightweight batch metadata ──
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS _Batches
        (
            batch_code      TEXT PRIMARY KEY,
            source_type     TEXT NOT NULL,
            molecule_count  INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
        """
    )

    conn.commit()


def make_dry_database(db_path: str | Path = DEFAULT_DRY_DB_PATH) -> Path:
    """Create or upgrade Dry database schema and return resolved db path."""
    resolved_db_path = Path(db_path).expanduser().resolve()
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_db_path))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _init_dry_schema(conn)

        now = _utc_now_text()
        conn.execute("PRAGMA user_version").fetchone()
        print(f"[{now}] Dry DB ready: {resolved_db_path}")
    finally:
        conn.close()

    return resolved_db_path


def get_existing_lab_ids(db_path: str | Path = DEFAULT_DRY_DB_PATH) -> dict[str, str]:
    """Return {SMILES: LabID} for all unique SMILES already in Info table."""
    p = Path(db_path)
    if not p.exists() or not p.is_file():
        return {}

    conn = sqlite3.connect(str(p))
    try:
        rows = conn.execute("SELECT DISTINCT SMILES, LabID FROM Info").fetchall()
        return {str(r[0]): str(r[1]) for r in rows}
    except Exception:
        return {}
    finally:
        conn.close()


def get_existing_batch_codes(db_path: str | Path = DEFAULT_DRY_DB_PATH) -> set[str]:
    """Return set of batch_code values already registered in _Batches."""
    p = Path(db_path)
    if not p.exists() or not p.is_file():
        return set()

    conn = sqlite3.connect(str(p))
    try:
        rows = conn.execute("SELECT batch_code FROM _Batches").fetchall()
        return {str(r[0]).strip() for r in rows if r and r[0]}
    except Exception:
        return set()
    finally:
        conn.close()


def get_next_lab_id_number(db_path: str | Path = DEFAULT_DRY_DB_PATH) -> int:
    """Return the next available LabID number (numeric part)."""
    p = Path(db_path)
    if not p.exists() or not p.is_file():
        return 1

    conn = sqlite3.connect(str(p))
    try:
        row = conn.execute(
            "SELECT MAX(CAST(SUBSTR(LabID, 2) AS INTEGER)) FROM Info WHERE LabID LIKE 'L%'"
        ).fetchone()
        return (row[0] or 0) + 1
    except Exception:
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    DB_PATH = r"E:\DryData\_validation\Dry_validation.db"
    resolved = make_dry_database(DB_PATH)
    print(f"Dry DB ready: {resolved}")
