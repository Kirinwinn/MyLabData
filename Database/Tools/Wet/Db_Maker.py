import datetime
import os
import sqlite3
from pathlib import Path


DEFAULT_IGNORE_DIRS = {
    ".ipynb_checkpoints",
    "RData",
    "PData",
    "SData",
    "__pycache__",
    ".git",
    "$RECYCLE.BIN",
    "System Volume Information",
}


def _init_wet_schema(conn):
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS batches
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exp_type TEXT,
            molecule TEXT,
            batch_name TEXT,
            date_str TEXT,
            note TEXT,
            folder_path TEXT,
            status TEXT,
            solvent TEXT,
            concentration TEXT,
            round TEXT,
            probe TEXT,
            last_updated TIMESTAMP
        )
        """
    )

    for col in ["status", "solvent", "concentration", "round", "probe"]:
        try:
            c.execute(f"ALTER TABLE batches ADD COLUMN {col} TEXT")
        except Exception:
            pass

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS files
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            category TEXT,
            filename TEXT,
            filepath TEXT,
            is_valid INTEGER,
            FOREIGN KEY(batch_id) REFERENCES batches(id)
        )
        """
    )
    conn.commit()


def _scan_wet_folders(conn, data_root, folder_parser, validator, ignore_dirs):
    c = conn.cursor()
    c.execute("DELETE FROM files")
    c.execute("DELETE FROM batches")

    for root, dirs, files in os.walk(data_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]

        for d in dirs:
            folder_path = os.path.join(root, d)
            meta = folder_parser.parse(d)
            if not meta:
                continue

            note_content = "> No readme.md found."
            for f in os.listdir(folder_path):
                if f.lower() == "readme.md":
                    try:
                        with open(os.path.join(folder_path, f), "r", encoding="utf-8") as md:
                            note_content = md.read()
                    except Exception:
                        pass
                    break

            c.execute(
                """
                INSERT INTO batches
                (exp_type, molecule, batch_name, date_str, note, folder_path, status, solvent, concentration, round, probe, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta["exp_type"],
                    meta["molecule"],
                    meta["batch_name"],
                    meta["date_str"],
                    note_content,
                    folder_path,
                    meta["status"],
                    meta.get("solvent", ""),
                    meta.get("conc", ""),
                    meta.get("round", ""),
                    meta.get("probe", ""),
                    datetime.datetime.now(),
                ),
            )
            batch_id = c.lastrowid

            for category in ["RData", "PData", "SData"]:
                cat_path = os.path.join(folder_path, category)
                if not os.path.exists(cat_path):
                    continue

                if meta["exp_type"] in ("SolventsCom", "SolventsComplete", "SolventsCheck", "IF-P", "Confocal1mage", "Confal1mage") and category == "RData":
                    for walk_root, walk_dirs, walk_files in os.walk(cat_path):
                        rel_dir = os.path.relpath(walk_root, cat_path)
                        parts = rel_dir.replace("\\", "/").split("/")
                        in_pics = any(part.endswith("_Pics") or part == "Pics" for part in parts)

                        for file in walk_files:
                            if file.startswith(".") or file.lower() == "readme.md":
                                continue
                            full_path = os.path.abspath(os.path.join(walk_root, file))
                            display_name = file if rel_dir == "." else os.path.join(rel_dir, file)

                            if in_pics:
                                is_valid = 1
                            else:
                                is_valid = 1 if validator.validate_filename_strict(file, meta["exp_type"]) else 0

                            c.execute(
                                "INSERT INTO files (batch_id, category, filename, filepath, is_valid) VALUES (?, ?, ?, ?, ?)",
                                (batch_id, category, display_name, full_path, is_valid),
                            )

                        if meta["exp_type"] in ("IF-P",):
                            for sub_d in walk_dirs:
                                sub_full = os.path.abspath(os.path.join(walk_root, sub_d))
                                sub_rel = sub_d if rel_dir == "." else os.path.join(rel_dir, sub_d)
                                c.execute(
                                    "INSERT INTO files (batch_id, category, filename, filepath, is_valid) VALUES (?, ?, ?, ?, ?)",
                                    (batch_id, category, sub_rel + "/", sub_full, 1),
                                )
                else:
                    for file in os.listdir(cat_path):
                        if file.startswith(".") or file.lower() == "readme.md":
                            continue
                        file_full = os.path.join(cat_path, file)
                        if not os.path.isfile(file_full):
                            continue

                        full_path = os.path.abspath(file_full)
                        is_valid = 1 if validator.validate_filename_strict(file, meta["exp_type"]) else 0
                        c.execute(
                            "INSERT INTO files (batch_id, category, filename, filepath, is_valid) VALUES (?, ?, ?, ?, ?)",
                            (batch_id, category, file, full_path, is_valid),
                        )

    conn.commit()


def make_wet_database(data_root, db_path, folder_parser, validator, ignore_dirs=None):
    resolved_data_root = Path(data_root)
    resolved_db_path = Path(db_path)
    effective_ignore_dirs = set(ignore_dirs) if ignore_dirs is not None else DEFAULT_IGNORE_DIRS

    print(f"[{datetime.datetime.now()}] Scanning: {resolved_data_root}")
    if not resolved_data_root.exists():
        return

    conn = sqlite3.connect(resolved_db_path)
    try:
        _init_wet_schema(conn)
        _scan_wet_folders(conn, str(resolved_data_root), folder_parser, validator, effective_ignore_dirs)
    finally:
        conn.close()

    print("Scan complete.")
