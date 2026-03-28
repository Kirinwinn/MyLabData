import sqlite3
import sys
from pathlib import Path

# Ensure project root is on path so sibling packages resolve.
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

DB_PATH = BASE_DIR / "Database" / "Wet" / "Wet.db"


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_molecules_with_types():
    conn = get_connection()
    try:
        molecules_rows = conn.execute(
            "SELECT DISTINCT molecule FROM batches ORDER BY molecule"
        ).fetchall()

        molecules = []
        for row in molecules_rows:
            mol_name = row["molecule"]
            types_rows = conn.execute(
                "SELECT DISTINCT exp_type FROM batches WHERE molecule = ? AND status = 'Normal'",
                (mol_name,)
            ).fetchall()
            molecules.append({
                "name": mol_name,
                "types": [t["exp_type"] for t in types_rows]
            })

        return molecules
    finally:
        conn.close()


def list_batches_by_molecule(molecule, exp_type=None, sort_mode="time"):
    conn = get_connection()
    try:
        query = "SELECT * FROM batches WHERE molecule = ?"
        params = [molecule]

        if exp_type:
            query += " AND exp_type = ?"
            params.append(exp_type)

        if sort_mode == "type":
            query += " ORDER BY exp_type ASC, date_str DESC, id DESC"
        else:
            query += " ORDER BY date_str DESC, id DESC"

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_files_by_batch(batch_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM files WHERE batch_id = ?",
            (batch_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_file_record(file_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_file_path(file_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT filepath FROM files WHERE id = ?", (file_id,)).fetchone()
        return row["filepath"] if row else None
    finally:
        conn.close()
