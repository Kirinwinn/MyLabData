import sqlite3
import sys
import re
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

DB_PATH = BASE_DIR / "Database" / "Wet" / "Wet.db"
SOLVENTSCOM_EXP_TYPES = {"solventscom", "solventscomplete", "solventscheck"}
FLUOSTABLE_EXP_TYPES = {"fluostable"}
UVSTABLE_EXP_TYPES = {"uvstable"}
MTT_EXP_TYPES = {"mtt"}
E_EXP_TYPES = {"e"}
SELECTIVEI_EXP_TYPES = {"selectivei"}
SOLVENT_OPTIONS = ["EtOH", "MeOH", "PBS", "EA", "MeCN", "DMSO", "DCM", "H2O"]


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _build_batch_label(row):
    date_str = str(row["date_str"] or "").strip()
    round_raw = str(row["round"] or "").strip()
    round_display = round_raw[:-5] if round_raw.lower().endswith("_time") else round_raw
    status = str(row["status"] or "").strip()

    parts = [p for p in [date_str, round_display] if p]
    label = " / ".join(parts) if parts else f"Batch #{row['id']}"
    if status and status.lower() != "normal":
        label = f"{label} ({status})"
    return label


def list_solventscom_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?, ?, ?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(SOLVENTSCOM_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def list_fluostable_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(FLUOSTABLE_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def list_uvstable_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(UVSTABLE_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def list_mtt_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(MTT_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def list_e_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(E_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def list_selectivei_molecules_with_batches():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE lower(exp_type) IN (?)
            ORDER BY molecule ASC, date_str DESC, id DESC
            """,
            tuple(SELECTIVEI_EXP_TYPES),
        ).fetchall()

        grouped = {}
        for row in rows:
            molecule = str(row["molecule"] or "").strip()
            if not molecule:
                continue
            bucket = grouped.setdefault(molecule, [])
            bucket.append(
                {
                    "batch_id": row["id"],
                    "label": _build_batch_label(row),
                    "date_str": row["date_str"],
                    "round": row["round"],
                    "status": row["status"],
                    "exp_type": row["exp_type"],
                }
            )

        return [
            {"molecule": molecule, "batches": batches}
            for molecule, batches in grouped.items()
        ]
    finally:
        conn.close()


def _get_type_profile(type_value):
    key = str(type_value or "solventscom").strip().lower()

    if key == "fluostable":
        return {
            "type": "fluostable",
            "pattern_options": [
                {"value": "cross", "label": "Cross"},
                {"value": "batch", "label": "Batch"},
            ],
            "default_pattern": "cross",
            "molecules": list_fluostable_molecules_with_batches(),
        }

    if key == "uvstable":
        return {
            "type": "uvstable",
            "pattern_options": [
                {"value": "cross", "label": "Cross"},
                {"value": "batch", "label": "Batch"},
            ],
            "default_pattern": "cross",
            "molecules": list_uvstable_molecules_with_batches(),
        }

    if key == "mtt":
        return {
            "type": "mtt",
            "pattern_options": [
                {"value": "cross", "label": "Cross"},
                {"value": "batch", "label": "Batch"},
            ],
            "default_pattern": "cross",
            "molecules": list_mtt_molecules_with_batches(),
        }

    if key == "e":
        return {
            "type": "e",
            "pattern_options": [
                {"value": "cross", "label": "Cross"},
                {"value": "batch", "label": "Batch"},
            ],
            "default_pattern": "cross",
            "molecules": list_e_molecules_with_batches(),
        }

    if key == "selectivei":
        return {
            "type": "selectivei",
            "pattern_options": [
                {"value": "cross", "label": "Cross"},
                {"value": "batch", "label": "Batch"},
            ],
            "default_pattern": "cross",
            "molecules": list_selectivei_molecules_with_batches(),
        }

    return {
        "type": "solventscom",
        "pattern_options": [
            {"value": "cross", "label": "Cross"},
            {"value": "batch", "label": "Batch"},
            {"value": "solvent", "label": "Solvent"},
        ],
        "default_pattern": "cross",
        "molecules": list_solventscom_molecules_with_batches(),
    }


def get_compare_init_payload():
    default_type = "solventscom"
    solventscom_profile = _get_type_profile("solventscom")
    fluostable_profile = _get_type_profile("fluostable")
    uvstable_profile = _get_type_profile("uvstable")
    mtt_profile = _get_type_profile("mtt")
    e_profile = _get_type_profile("e")
    selectivei_profile = _get_type_profile("selectivei")

    return {
        "type_options": [
            {"value": "solventscom", "label": "SolventsCom"},
            {"value": "fluostable", "label": "FluoStable"},
            {"value": "uvstable", "label": "UVStable"},
            {"value": "mtt", "label": "MTT"},
            {"value": "e", "label": "e"},
            {"value": "selectivei", "label": "SelectiveI"},
        ],
        "default_type": default_type,
        "pattern_options": solventscom_profile["pattern_options"],
        "default_pattern": solventscom_profile["default_pattern"],
        "solvent_options": SOLVENT_OPTIONS,
        "molecules": solventscom_profile["molecules"],
        "type_profiles": {
            "solventscom": solventscom_profile,
            "fluostable": fluostable_profile,
            "uvstable": uvstable_profile,
            "mtt": mtt_profile,
            "e": e_profile,
            "selectivei": selectivei_profile,
        },
    }


def get_solventscom_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?, ?, ?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(SOLVENTSCOM_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_fluostable_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(FLUOSTABLE_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_uvstable_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(UVSTABLE_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_mtt_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(MTT_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_e_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(E_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_selectivei_batches_for_molecule(molecule):
    molecule = str(molecule or "").strip()
    if not molecule:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, molecule, date_str, round, status, exp_type
            FROM batches
            WHERE molecule = ?
              AND lower(exp_type) IN (?)
            ORDER BY date_str DESC, id DESC
            """,
            (molecule, *tuple(SELECTIVEI_EXP_TYPES)),
        ).fetchall()

        return [
            {
                "batch_id": row["id"],
                "label": _build_batch_label(row),
                "date_str": row["date_str"],
                "round": row["round"],
                "status": row["status"],
                "exp_type": row["exp_type"],
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_batches_for_molecule(molecule, type_value="solventscom"):
    key = str(type_value or "solventscom").strip().lower()
    if key == "fluostable":
        return get_fluostable_batches_for_molecule(molecule)
    if key == "uvstable":
        return get_uvstable_batches_for_molecule(molecule)
    if key == "mtt":
        return get_mtt_batches_for_molecule(molecule)
    if key == "e":
        return get_e_batches_for_molecule(molecule)
    if key == "selectivei":
        return get_selectivei_batches_for_molecule(molecule)
    return get_solventscom_batches_for_molecule(molecule)


def _pick_e_working_columns(df):
    if df is None or df.empty:
        return None, None

    headers = list(df.columns)
    normalized = {h: re.sub(r"[^a-z0-9]", "", str(h).lower()) for h in headers}

    conc_col = None
    abs_col = None

    for col in headers:
        key = normalized[col]
        if conc_col is None and ("concentration" in key or "conc" in key):
            conc_col = col
        if abs_col is None and ("absorbance" in key or key == "abs" or "abs" in key):
            abs_col = col

    if conc_col is None and headers:
        conc_col = headers[0]
    if abs_col is None:
        for col in headers:
            if col == conc_col:
                continue
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() >= max(3, len(df) // 3):
                abs_col = col
                break

    return conc_col, abs_col


def _extract_e_working_points_from_df(df):
    if df is None or df.empty:
        return []

    conc_col, abs_col = _pick_e_working_columns(df)
    if conc_col is None or abs_col is None:
        return []

    conc_values = pd.to_numeric(df[conc_col], errors="coerce")
    abs_values = pd.to_numeric(df[abs_col], errors="coerce")
    valid = conc_values.notna() & abs_values.notna()
    if valid.sum() < 2:
        return []

    points = [[float(x), float(y)] for x, y in zip(conc_values[valid], abs_values[valid])]
    points.sort(key=lambda p: p[0])
    return points


def _extract_e_fit_meta_from_markdown(text):
    content = str(text or "")

    e_value = ""
    log10e_value = ""
    slope = None
    intercept = None
    equation_text = ""
    r2_value = ""

    for raw_line in content.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue

        compact = re.sub(r"\s+", "", line).lower()
        if not log10e_value:
            match_loge = re.match(r"^log10e=([+-]?\d+(?:\.\d+)?)$", compact)
            if match_loge:
                log10e_value = match_loge.group(1).strip()
                continue

        if not e_value:
            match_e = re.match(r"^e=([+-]?\d+(?:\.\d+)?)$", compact)
            if match_e:
                e_value = match_e.group(1).strip()

    match_eq = re.search(
        r"y\s*=\s*([+-]?\d+(?:\.\d+)?)\s*x\s*([+-]\s*\d+(?:\.\d+)?)",
        content,
        re.IGNORECASE,
    )
    if match_eq:
        slope = float(match_eq.group(1))
        intercept = float(match_eq.group(2).replace(" ", ""))
        sign = "+" if intercept >= 0 else "-"
        equation_text = f"y = {slope:.6g}x {sign} {abs(intercept):.6g}"

    match_r2 = re.search(r"r\s*(?:\^\s*2|²)\s*=\s*([+-]?\d+(?:\.\d+)?)", content, re.IGNORECASE)
    if match_r2:
        r2_value = match_r2.group(1).strip()

    return {
        "e": e_value,
        "log10e": log10e_value,
        "fit_equation": equation_text,
        "slope": slope,
        "intercept": intercept,
        "r2": r2_value,
    }


def extract_e_meta_from_sdata_markdowns(markdown_records):
    merged = {
        "e": "",
        "log10e": "",
        "fit_equation": "",
        "slope": None,
        "intercept": None,
        "r2": "",
    }

    for rec in markdown_records or []:
        text = str((rec or {}).get("text") or "")
        if not text:
            continue

        parsed = _extract_e_fit_meta_from_markdown(text)
        if parsed.get("e"):
            merged["e"] = parsed["e"]
        if parsed.get("log10e"):
            merged["log10e"] = parsed["log10e"]
        if parsed.get("fit_equation"):
            merged["fit_equation"] = parsed["fit_equation"]
        if parsed.get("slope") is not None:
            merged["slope"] = parsed["slope"]
        if parsed.get("intercept") is not None:
            merged["intercept"] = parsed["intercept"]
        if parsed.get("r2"):
            merged["r2"] = parsed["r2"]

    return merged


def extract_dynamic_e_series_from_pdata_files(files_rows):
    """Parse e concentration-absorbance points from PData Working files."""
    series_payload = []
    allowed_exts = {".csv", ".xlsx", ".xls"}

    for item in files_rows or []:
        filename = str(item.get("filename") or "")
        filepath = str(item.get("filepath") or "")
        category = str(item.get("category") or "").strip().lower()
        if not filename or not filepath:
            continue
        if category != "pdata":
            continue

        name_lower = filename.lower()
        if "working" not in name_lower:
            continue
        if "_e_" not in name_lower and not re.search(r"(^|[^a-z0-9])e([^a-z0-9]|$)", name_lower):
            continue

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            continue

        try:
            table_frames = _read_table_frames(filepath)
            preferred = [f for f in table_frames if str(f[0] or "").strip().lower() == "working"]
            fallback = [f for f in table_frames if f not in preferred]
            ordered_frames = preferred + fallback

            for sheet_name, frame in ordered_frames:
                points = _extract_e_working_points_from_df(frame)
                if not points:
                    continue

                sheet_prefix = str(sheet_name or "").strip()
                file_label = filename if not sheet_prefix else f"{filename}#{sheet_prefix}"
                series_payload.append(
                    {
                        "file_id": int(item.get("id") or 0),
                        "filename": file_label,
                        "kind": "e",
                        "curves": [
                            {
                                "name": "Abs",
                                "points": points,
                            }
                        ],
                    }
                )
                break
        except Exception:
            continue

    return series_payload


def _canonical_solvent(value, solvent_options):
    text = str(value or "").strip().lower()
    if not text:
        return ""

    for solvent in solvent_options:
        token = solvent.lower()
        if text == token or token in text:
            return solvent
    return ""


def _normalize_header_name(header):
    key = re.sub(r"[^a-z0-9\u03bb]", "", str(header or "").lower())
    if "solvent" in key:
        return "solvent"
    if "\u03bb" in key or "lambdamax" in key or "lmax" in key:
        return "lambda_max"
    if "emission" in key or key == "em":
        return "emission"
    if "excitation" in key or key == "ex":
        return "excitation"
    return ""


def _split_pipe_row(line):
    line = str(line or "").strip()
    if "|" not in line:
        return None
    cells = [c.strip() for c in line.strip("|").split("|")]
    return cells if len(cells) >= 2 else None


def _is_markdown_separator_row(cells):
    if not cells:
        return False
    for c in cells:
        token = c.replace(" ", "")
        if not token:
            continue
        if not re.fullmatch(r":?-{3,}:?", token):
            return False
    return True


def _extract_from_markdown_tables(text, solvent_options):
    results = {}
    lines = str(text or "").splitlines()
    i = 0
    total = len(lines)

    while i < total - 1:
        header_cells = _split_pipe_row(lines[i])
        sep_cells = _split_pipe_row(lines[i + 1])

        if not header_cells or not sep_cells or len(header_cells) != len(sep_cells) or not _is_markdown_separator_row(sep_cells):
            i += 1
            continue

        index_map = {}
        for idx, head in enumerate(header_cells):
            normalized = _normalize_header_name(head)
            if normalized:
                index_map[normalized] = idx

        if "solvent" not in index_map:
            i += 1
            continue

        row_idx = i + 2
        while row_idx < total:
            row_cells = _split_pipe_row(lines[row_idx])
            if not row_cells or len(row_cells) < len(header_cells):
                break

            solvent = _canonical_solvent(row_cells[index_map["solvent"]], solvent_options)
            if solvent:
                bucket = results.setdefault(solvent, {"lambda_max": "", "emission": "", "excitation": ""})
                for key in ("lambda_max", "emission", "excitation"):
                    col_idx = index_map.get(key)
                    if col_idx is None:
                        continue
                    value = str(row_cells[col_idx] or "").strip()
                    if value:
                        bucket[key] = value
            row_idx += 1

        i = row_idx

    return results


def _extract_from_lines(text, solvent_options):
    results = {}
    patterns = {
        "lambda_max": re.compile(r"(?:\u03bb\s*max|lambdamax|lambda\s*max|lmax)\s*[:=]?\s*([^,;|]+)", re.IGNORECASE),
        "emission": re.compile(r"(?:emission|\bem\b)\s*[:=]?\s*([^,;|]+)", re.IGNORECASE),
        "excitation": re.compile(r"(?:excitation|\bex\b)\s*[:=]?\s*([^,;|]+)", re.IGNORECASE),
    }

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        solvent = _canonical_solvent(line, solvent_options)
        if not solvent:
            continue

        bucket = results.setdefault(solvent, {"lambda_max": "", "emission": "", "excitation": ""})
        for key, pat in patterns.items():
            match = pat.search(line)
            if match:
                value = str(match.group(1) or "").strip()
                if value:
                    bucket[key] = value

    return results


def extract_number_table_from_sdata_markdowns(markdown_records, solvent_options=None):
    """Build solvent-indexed Number table values from SData markdown files.

    Returns rows for each solvent with lambda_max/emission/excitation values.
    """
    options = list(solvent_options or SOLVENT_OPTIONS)
    merged = {s: {"lambda_max": "", "emission": "", "excitation": ""} for s in options}

    for rec in markdown_records or []:
        text = str((rec or {}).get("text") or "")
        if not text:
            continue

        table_data = _extract_from_markdown_tables(text, options)
        line_data = _extract_from_lines(text, options)

        for source in (table_data, line_data):
            for solvent, values in source.items():
                bucket = merged.setdefault(solvent, {"lambda_max": "", "emission": "", "excitation": ""})
                for key in ("lambda_max", "emission", "excitation"):
                    val = str(values.get(key) or "").strip()
                    if val:
                        bucket[key] = val

    rows = []
    for solvent in options:
        values = merged.get(solvent, {"lambda_max": "", "emission": "", "excitation": ""})
        rows.append({
            "solvent": solvent,
            "lambda_max": values.get("lambda_max", ""),
            "emission": values.get("emission", ""),
            "excitation": values.get("excitation", ""),
        })

    return rows


def _read_table_frames(file_path):
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        try:
            return [("", pd.read_csv(path, encoding="utf-8"))]
        except UnicodeDecodeError:
            return [("", pd.read_csv(path, encoding="gbk"))]

    if ext in (".xlsx", ".xls"):
        sheets = pd.read_excel(path, sheet_name=None)
        frames = []
        for sheet_name, frame in (sheets or {}).items():
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frames.append((str(sheet_name), frame))
        return frames

    return []


def _infer_curve_kind(filename, sheet_name=""):
    scope = f"{str(filename or '').lower()} {str(sheet_name or '').lower()}"

    if any(token in scope for token in ("uv", "abs", "absorption")):
        return "uv"
    if any(token in scope for token in ("fluo", "emission", "excitation", "fluoem", "fluoex")):
        return "fluo"
    if re.search(r"(^|[^a-z0-9])(em|ex)([^a-z0-9]|$)", scope):
        return "fluo"
    return "fin"


def _pick_x_column(df):
    if df is None or df.empty:
        return None

    headers = list(df.columns)
    normalized = {h: re.sub(r"[^a-z0-9\u03bb]", "", str(h).lower()) for h in headers}

    preferred_tokens = ("wavelength", "nm", "lambda", "\u03bb", "wave", "x")
    for col in headers:
        key = normalized[col]
        if any(tok in key for tok in preferred_tokens):
            return col

    for col in headers:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() >= max(10, len(df) // 3):
            return col

    return None


def _extract_curves_from_df(df):
    if df is None or df.empty:
        return []

    x_col = _pick_x_column(df)
    if x_col is None:
        return []

    x_values = pd.to_numeric(df[x_col], errors="coerce")
    curves = []

    for col in df.columns:
        if col == x_col:
            continue

        col_name = str(col or "").strip()
        norm_name = re.sub(r"[^a-z0-9]", "", col_name.lower())
        if not norm_name:
            continue
        # Filter metadata/noise columns that frequently appear in Working exports.
        if (
            "unnamed" in norm_name
            or "file" in norm_name
            or "name" in norm_name
            or "created" in norm_name
            or "blank" in norm_name
            or norm_name in {"nm", "to", "1"}
        ):
            continue

        y_values = pd.to_numeric(df[col], errors="coerce")
        valid = x_values.notna() & y_values.notna()
        if valid.sum() < 20:
            continue

        xv = x_values[valid].astype(float)
        yv = y_values[valid].astype(float)
        x_diff = xv.diff().dropna()
        if len(x_diff) == 0 or float((x_diff > 0).mean()) < 0.75:
            continue
        if float(xv.max() - xv.min()) < 40:
            continue
        if float(yv.std()) <= 1e-8:
            continue

        curve_points = [[float(x), float(y)] for x, y in zip(xv, yv)]
        if not curve_points:
            continue

        curves.append({
            "name": col_name,
            "points": curve_points,
        })

    return curves


def _pick_curve_name_from_raw_table(raw_df, y_col_idx):
    max_scan_rows = min(20, len(raw_df))
    bad_tokens = {
        "file", "name", "name:", "wavelength", "intensity", "created:",
        "data:", "instrument:", "spectrum", "scan", "sample", "slit",
        "speed", "response", "shutter:", "type:", "range:", "(nm)",
    }

    for ridx in range(max_scan_rows):
        value = raw_df.iat[ridx, y_col_idx] if y_col_idx < raw_df.shape[1] else None
        text = str(value or "").strip()
        if not text:
            continue
        token = text.lower()
        if token in bad_tokens:
            continue
        if token.startswith("unnamed"):
            continue
        if token in {"nan", "none"}:
            continue
        return text

    return f"curve_{y_col_idx + 1}"


def _extract_curves_from_working_raw_blocks(file_path, sheet_name):
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in (".xlsx", ".xls"):
        return []

    raw_df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if raw_df is None or raw_df.empty:
        return []

    curves = []
    seen_names = set()

    # In these sheets, data often appears as repeated [meta, wavelength, intensity, ...] blocks.
    for x_idx in range(0, max(0, raw_df.shape[1] - 1)):
        y_idx = x_idx + 1
        x_series = pd.to_numeric(raw_df.iloc[:, x_idx], errors="coerce")
        y_series = pd.to_numeric(raw_df.iloc[:, y_idx], errors="coerce")
        valid = x_series.notna() & y_series.notna()
        if valid.sum() < 25:
            continue

        xv = x_series[valid].astype(float)
        yv = y_series[valid].astype(float)

        x_diff = xv.diff().dropna()
        if len(x_diff) == 0 or float((x_diff > 0).mean()) < 0.75:
            continue
        if float(xv.max() - xv.min()) < 40:
            continue
        if float(yv.std()) <= 1e-8:
            continue

        curve_name = _pick_curve_name_from_raw_table(raw_df, y_idx)
        dedupe_key = re.sub(r"[^a-z0-9]", "", curve_name.lower())
        if not dedupe_key or dedupe_key in seen_names:
            continue
        seen_names.add(dedupe_key)

        points = [[float(x), float(y)] for x, y in zip(xv, yv)]
        if not points:
            continue

        curves.append({"name": curve_name, "points": points})

    return curves


def _pick_time_column(df):
    if df is None or df.empty:
        return None

    headers = list(df.columns)
    normalized = {h: re.sub(r"[^a-z0-9]", "", str(h).lower()) for h in headers}

    preferred_tokens = ("time", "sec", "min")
    for col in headers:
        key = normalized[col]
        if any(tok in key for tok in preferred_tokens):
            return col

    for col in headers:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() >= max(5, len(df) // 3):
            return col

    return None


def _extract_uvstable_curves_from_df(df):
    if df is None or df.empty:
        return []

    x_col = _pick_time_column(df)
    if x_col is None:
        return []

    x_values = pd.to_numeric(df[x_col], errors="coerce")
    curves = []

    for col in df.columns:
        if col == x_col:
            continue

        y_values = pd.to_numeric(df[col], errors="coerce")
        valid = x_values.notna() & y_values.notna()
        if valid.sum() < 5:
            continue

        xv = x_values[valid].astype(float)
        yv = y_values[valid].astype(float)

        x_diff = xv.diff().dropna()
        if len(x_diff) > 0 and float((x_diff >= 0).mean()) < 0.6:
            continue
        if float(yv.std()) <= 1e-10:
            continue

        curve_points = [[float(x), float(y)] for x, y in zip(xv, yv)]
        if not curve_points:
            continue

        curves.append({
            "name": str(col),
            "points": curve_points,
        })

    return curves


def extract_dynamic_uvstable_series_from_pdata_files(files_rows):
    """Parse UVStable time-absorbance curves from PData Working files."""
    series_payload = []
    allowed_exts = {".csv", ".xlsx", ".xls"}

    for item in files_rows or []:
        filename = str(item.get("filename") or "")
        filepath = str(item.get("filepath") or "")
        category = str(item.get("category") or "").strip().lower()

        if not filename or not filepath:
            continue
        if category != "pdata":
            continue

        name_lower = filename.lower()
        if "uvstable" not in name_lower or "working" not in name_lower:
            continue

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            continue

        try:
            table_frames = _read_table_frames(filepath)
            for sheet_name, frame in table_frames:
                curves = _extract_uvstable_curves_from_df(frame)
                if not curves:
                    continue

                normalized_curves = []
                sheet_prefix = str(sheet_name or "").strip()
                for curve in curves:
                    curve_name = str(curve.get("name") or "").strip() or "Abs"
                    if sheet_prefix:
                        curve_name = f"{sheet_prefix}:{curve_name}"
                    normalized_curves.append({
                        "name": curve_name,
                        "points": curve.get("points") or [],
                    })

                file_label = filename if not sheet_prefix else f"{filename}#{sheet_prefix}"
                series_payload.append({
                    "file_id": int(item.get("id") or 0),
                    "filename": file_label,
                    "kind": "uvstable",
                    "curves": normalized_curves,
                })
        except Exception:
            continue

    return series_payload


def _extract_selectivei_bars_from_df(df):
    if df is None or df.empty:
        return []

    bars = []
    for col in df.columns:
        label = str(col or "").strip()
        norm = re.sub(r"[^a-z0-9]", "", label.lower())
        if not norm:
            continue

        # Drop common metadata or baseline columns that should not appear as groups.
        if (
            "unnamed" in norm
            or "file" in norm
            or "name" in norm
            or "created" in norm
            or "wavelength" in norm
            or norm == "blank"
        ):
            continue

        values = pd.to_numeric(df[col], errors="coerce").dropna().astype(float)
        if values.empty:
            continue

        n = int(len(values))
        mean_val = float(values.mean())
        std_val = float(values.std(ddof=1)) if n > 1 else 0.0
        sem_val = float(std_val / (n ** 0.5)) if n > 1 else 0.0

        bars.append(
            {
                "label": label,
                "mean": mean_val,
                "error": sem_val,
                "std": std_val,
                "n": n,
            }
        )

    return bars


def extract_dynamic_selectivei_series_from_pdata_files(files_rows):
    """Parse SelectiveI grouped intensity bars from PData *Working files."""
    payload = []
    allowed_exts = {".xlsx", ".xls", ".csv"}

    for item in files_rows or []:
        filename = str(item.get("filename") or "")
        filepath = str(item.get("filepath") or "")
        category = str(item.get("category") or "").strip().lower()
        if not filename or not filepath:
            continue
        if category != "pdata":
            continue

        name_lower = filename.lower()
        if "selectivei" not in name_lower:
            continue
        if not re.search(r"(?:^|[^a-z0-9])working\.(xlsx|xls|csv)$", name_lower):
            continue

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            continue

        try:
            table_frames = _read_table_frames(filepath)
            preferred = [f for f in table_frames if str(f[0] or "").strip().lower() == "working"]
            fallback = [f for f in table_frames if f not in preferred]
            ordered_frames = preferred + fallback

            for sheet_name, frame in ordered_frames:
                bars = _extract_selectivei_bars_from_df(frame)
                if not bars:
                    continue

                sheet_prefix = str(sheet_name or "").strip()
                file_label = filename if not sheet_prefix else f"{filename}#{sheet_prefix}"
                payload.append(
                    {
                        "file_id": int(item.get("id") or 0),
                        "filename": file_label,
                        "kind": "selectivei",
                        "source": "working",
                        "bars": bars,
                    }
                )
                break
        except Exception:
            continue

    return payload


def _normalize_mtt_concentration_label(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    text = str(value).strip()
    if not text:
        return ""

    if text.lower() == "control":
        return "Control"

    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(numeric):
        num = float(numeric)
        if abs(num) <= 1e-12:
            return "Control"
        return f"{num:g}"

    if text.lower() in {"ctrl", "ctl"}:
        return "Control"

    return text


def _extract_mtt_bars_from_df(df):
    if df is None or df.empty or len(df.index) < 2:
        return []

    first_row = list(df.iloc[0, :])
    bars = []

    for col_idx, raw_label in enumerate(first_row):
        label = _normalize_mtt_concentration_label(raw_label)
        if not label:
            continue

        values = pd.to_numeric(df.iloc[1:, col_idx], errors="coerce").dropna().astype(float)
        if values.empty:
            continue

        n = int(len(values))
        mean_val = float(values.mean())
        std_val = float(values.std(ddof=1)) if n > 1 else 0.0
        sem_val = float(std_val / (n ** 0.5)) if n > 1 else 0.0

        conc_numeric = None
        if label != "Control":
            parsed = pd.to_numeric(pd.Series([label]), errors="coerce").iloc[0]
            if pd.notna(parsed):
                conc_numeric = float(parsed)

        bars.append(
            {
                "label": label,
                "mean": mean_val,
                "error": sem_val,
                "std": std_val,
                "n": n,
                "concentration": conc_numeric,
            }
        )

    return bars


def extract_dynamic_mtt_series_from_pdata_files(files_rows):
    """Parse MTT bar/error datasets from PData Working/Ref PerData sheets."""
    payload = []
    allowed_exts = {".xlsx", ".xls", ".csv"}

    for item in files_rows or []:
        filename = str(item.get("filename") or "")
        filepath = str(item.get("filepath") or "")
        category = str(item.get("category") or "").strip().lower()
        if not filename or not filepath:
            continue
        if category != "pdata":
            continue

        name_lower = filename.lower()
        if "mtt" not in name_lower:
            continue
        if "working" not in name_lower and "ref" not in name_lower:
            continue

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            continue

        try:
            bars = []
            sheet_label = "PerData"

            if ext in {".xlsx", ".xls"}:
                workbook = pd.ExcelFile(filepath)
                perdata_sheet = None
                for sn in workbook.sheet_names:
                    if str(sn).strip().lower() == "perdata":
                        perdata_sheet = sn
                        break
                if not perdata_sheet:
                    continue
                frame = pd.read_excel(filepath, sheet_name=perdata_sheet, header=None)
                bars = _extract_mtt_bars_from_df(frame)
                sheet_label = str(perdata_sheet)
            else:
                frame = pd.read_csv(filepath, header=None)
                bars = _extract_mtt_bars_from_df(frame)
                sheet_label = "PerData"

            if not bars:
                continue

            source = "working" if "working" in name_lower else "ref"
            file_label = filename if not sheet_label else f"{filename}#{sheet_label}"

            payload.append(
                {
                    "file_id": int(item.get("id") or 0),
                    "filename": file_label,
                    "kind": "mtt",
                    "source": source,
                    "bars": bars,
                }
            )
        except Exception:
            continue

    return payload


def extract_dynamic_fin_series_from_sdata_files(sdata_files):
    """Parse dynamic curve tables from PData Working records and return curve series payload."""
    series_payload = []
    allowed_exts = {".csv", ".xlsx", ".xls"}

    for item in sdata_files or []:
        filename = str(item.get("filename") or "")
        filepath = str(item.get("filepath") or "")
        category = str(item.get("category") or "").strip().lower()
        if not filename or not filepath:
            continue

        # User requirement: dynamic source must come from PData Working files only.
        if category != "pdata":
            continue
        if "working" not in filename.lower():
            continue

        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            continue

        try:
            table_frames = _read_table_frames(filepath)
            for sheet_name, frame in table_frames:
                curves = _extract_curves_from_df(frame)
                if not curves:
                    curves = _extract_curves_from_working_raw_blocks(filepath, sheet_name)
                if not curves:
                    continue

                normalized_curves = []
                sheet_prefix = str(sheet_name or "").strip()
                for curve in curves:
                    curve_name = str(curve.get("name") or "").strip() or "curve"
                    if sheet_prefix:
                        curve_name = f"{sheet_prefix}:{curve_name}"
                    normalized_curves.append({
                        "name": curve_name,
                        "points": curve.get("points") or [],
                    })

                file_label = filename if not sheet_prefix else f"{filename}#{sheet_prefix}"
                series_payload.append({
                    "file_id": int(item.get("id") or 0),
                    "filename": file_label,
                    "kind": _infer_curve_kind(filename, sheet_name),
                    "curves": normalized_curves,
                })
        except Exception:
            continue

    return series_payload
