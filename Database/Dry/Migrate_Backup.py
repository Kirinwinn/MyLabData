"""Migrate prepared DryData from BuExperimentData into ExperiData.

The backup tree is read-only. Molecule Parquets are copied, while trait and
prediction files are rewritten as query-ready Parquet with a registry LabID.
All destination writes use temporary files followed by an atomic rename.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from typing import Any

import duckdb

from .Registry import DryRegistry, _json_value, _sql_literal
from .Registry_Seed import seed_registry


BACKUP_ROOT = Path(
    os.getenv(
        "BU_EXPERIMENT_DATA_ROOT",
        r"C:\Users\cenking\Documents\BuExperimentData",
    )
).resolve()
BACKUP_DRY = BACKUP_ROOT / "DryData"

PREDICTION_SCHEMAS: dict[str, dict[str, str]] = {
    "DeepMPP": {
        "SMILES": "VARCHAR",
        "Abs_pred": "DOUBLE",
        "Emi_pred": "DOUBLE",
        "Solvent": "VARCHAR",
    },
    "Proby": {
        "SMILES": "VARCHAR",
        "abs": "DOUBLE",
        "emi": "DOUBLE",
        "plqy": "DOUBLE",
        "e": "DOUBLE",
        "log10e": "DOUBLE",
        "lifetime": "DOUBLE",
        "abs_fwhm_cm": "DOUBLE",
        "emi_fwhm_cm": "DOUBLE",
        "abs_fwhm_nm": "DOUBLE",
        "emi_fwhm_nm": "DOUBLE",
        "Solvent": "VARCHAR",
    },
    "Tox21": {
        "SMILES": "VARCHAR",
        "NR-AR": "DOUBLE",
        "NR-AR-LBD": "DOUBLE",
        "NR-AhR": "DOUBLE",
        "NR-Aromatase": "DOUBLE",
        "NR-ER": "DOUBLE",
        "NR-ER-LBD": "DOUBLE",
        "NR-PPAR-gamma": "DOUBLE",
        "SR-ARE": "DOUBLE",
        "SR-ATAD5": "DOUBLE",
        "SR-HSE": "DOUBLE",
        "SR-MMP": "DOUBLE",
        "SR-p53": "DOUBLE",
    },
}


def _copy_atomic(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Existing target size differs from source: {target}")
        return "existing"

    temporary = target.with_name(target.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Incomplete copy: {source} -> {temporary}")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return "copied"


def _is_registered(registry: DryRegistry, target: Path, category: str) -> bool:
    connection = registry.connect(read_only=True)
    try:
        row = connection.execute(
            """
            SELECT 1 FROM Imports
            WHERE status = 'completed' AND data_category = ? AND processed_path = ?
            LIMIT 1
            """,
            [category, str(target.resolve())],
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _set_original_path(
    registry: DryRegistry, import_id: int, source: Path, metadata: Any = None
) -> None:
    connection = registry.connect()
    try:
        connection.execute(
            """
            UPDATE Imports SET input_path = ?, original_filename = ?, metadata = ?
            WHERE import_id = ?
            """,
            [str(source.resolve()), source.name, _json_value(metadata), import_id],
        )
    finally:
        connection.close()


def _migration_connection(registry: DryRegistry) -> duckdb.DuckDBPyConnection:
    cache = registry.dry_root / "Cache" / "duckdb_temp"
    cache.mkdir(parents=True, exist_ok=True)
    connection = registry.connect()
    connection.execute("SET threads = 8")
    connection.execute("SET memory_limit = '12GB'")
    connection.execute(f"SET temp_directory = {_sql_literal(str(cache))}")
    connection.execute("SET preserve_insertion_order = false")
    return connection


def _copy_query_to_parquet(
    registry: DryRegistry, query: str, target: Path
) -> tuple[str, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        connection = duckdb.connect()
        try:
            count = int(connection.execute(
                f"SELECT count(*) FROM read_parquet({_sql_literal(str(target))})"
            ).fetchone()[0])
        finally:
            connection.close()
        return "existing", count

    temporary = target.with_name(target.stem + ".tmp.parquet")
    temporary.unlink(missing_ok=True)
    connection = _migration_connection(registry)
    try:
        row = connection.execute(
            f"""
            COPY ({query}) TO {_sql_literal(str(temporary))}
            (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880)
            """
        ).fetchone()
        output_rows = int(row[0])
        temporary.replace(target)
        return "converted", output_rows
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def migrate_molecules(registry: DryRegistry) -> list[dict[str, Any]]:
    results = []
    for source_class, title in (("external", "External"), ("generated", "Generated")):
        source = BACKUP_DRY / "Formal" / f"Formal_{title}.parquet"
        target = (
            registry.dry_root / "Processed" / "Molecules" / title
            / f"Formal_{title}.parquet"
        )
        copy_status = _copy_atomic(source, target)
        if _is_registered(registry, target, "molecules"):
            results.append({"file": str(target), "status": "already_registered"})
            continue
        result = registry.import_molecules(
            target,
            source_key=f"molecules.formal.{source_class}",
            source_name=f"Formal {title} Molecules",
            source_type=source_class,
            source_class=source_class,
            calculate_checksum=True,
        )
        _set_original_path(
            registry,
            result["import_id"],
            source,
            {"copy_status": copy_status, "authority": "Formal"},
        )
        results.append(result)
    return results


def migrate_traits(registry: DryRegistry) -> list[dict[str, Any]]:
    results = []
    source_id = registry.register_source(
        "toolscom.property",
        "ToolsCom Property",
        "system",
        description="Calculated molecular properties from ToolsCom.",
    )
    registry.register_attribute(
        "annotation.Property.calc_ok", "Calculation status", "annotation", "integer",
        source_id=source_id,
    )
    registry.register_attribute(
        "annotation.Property.error_message", "Calculation error", "annotation", "string",
        source_id=source_id,
    )

    for source_class, title in (("external", "External"), ("generated", "Generated")):
        source = BACKUP_DRY / "Property" / f"Property_{title}.parquet"
        target = (
            registry.dry_root / "Processed" / "Traits" / title
            / f"Property_{title}.parquet"
        )
        query = f"""
            SELECT molecule.lab_id, property.*
            FROM read_parquet({_sql_literal(str(source))}) property
            JOIN Molecules molecule
              ON molecule.canonical_smiles = property.SMILES
        """
        conversion, output_rows = _copy_query_to_parquet(registry, query, target)
        if _is_registered(registry, target, "traits"):
            results.append({
                "file": str(target), "status": "already_registered",
                "rows": output_rows,
            })
            continue
        result = registry.register_attribute_file(
            target,
            source_key="toolscom.property",
            source_name="ToolsCom Property",
            source_type="system",
            source_class=source_class,
            attribute_category="trait",
            attribute_prefix="Property",
            exclude_columns=("calc_ok", "error_message"),
            calculate_checksum=True,
            validate_identities=False,
        )
        _set_original_path(
            registry,
            result["import_id"],
            source,
            {"conversion": conversion, "joined_rows": output_rows},
        )
        results.append(result)
    return results


def _columns_struct(columns: dict[str, str]) -> str:
    pairs = ", ".join(
        f"{_sql_literal(name)}: {_sql_literal(data_type)}"
        for name, data_type in columns.items()
    )
    return "{" + pairs + "}"


def migrate_predictions(
    registry: DryRegistry, models: list[str] | None = None
) -> list[dict[str, Any]]:
    results = []
    selected_models = models or list(PREDICTION_SCHEMAS)
    for model in selected_models:
        if model not in PREDICTION_SCHEMAS:
            raise ValueError(f"Unknown model: {model}")
        source_id = registry.register_source(
            f"model.{model.lower()}", model, "derived",
            description=f"Prediction attributes produced by {model}.",
        )
        columns = PREDICTION_SCHEMAS[model]
        columns_struct = _columns_struct(columns)
        parallel_csv = "false" if model == "Proby" else "true"

        for source_class, title in (("external", "External"), ("generated", "Generated")):
            source = BACKUP_DRY / "Prediction" / model / f"{model}_{title}.csv"
            target = (
                registry.dry_root / "Processed" / "Predictions" / model
                / f"{model}_{title}.parquet"
            )
            reader = (
                f"read_csv({_sql_literal(str(source))}, header=true, "
                f"columns={columns_struct}, delim=',', nullstr='', "
                f"strict_mode=false, parallel={parallel_csv})"
            )
            query = f"""
                SELECT molecule.lab_id, prediction.*
                FROM {reader} prediction
                JOIN Molecules molecule
                  ON molecule.canonical_smiles = prediction.SMILES
                WHERE prediction.SMILES IS NOT NULL
                  AND trim(prediction.SMILES) <> ''
                  AND prediction.SMILES <> 'SMILES'
            """
            conversion, output_rows = _copy_query_to_parquet(registry, query, target)
            if _is_registered(registry, target, "predictions"):
                results.append({
                    "file": str(target), "status": "already_registered",
                    "rows": output_rows,
                })
                continue
            result = registry.register_attribute_file(
                target,
                source_key=f"model.{model.lower()}",
                source_name=model,
                source_type="derived",
                source_class=source_class,
                attribute_category="prediction",
                attribute_prefix=model,
                model_name=model,
                exclude_columns=("Solvent",),
                calculate_checksum=True,
                validate_identities=False,
            )
            _set_original_path(
                registry,
                result["import_id"],
                source,
                {
                    "conversion": conversion,
                    "joined_rows": output_rows,
                    "identity_key": "SMILES+Solvent" if "Solvent" in columns else "SMILES",
                },
            )
            results.append(result)
    return results


def refresh_views(registry: DryRegistry) -> list[str]:
    """Create lazy DuckDB views over migrated Parquet files."""
    view_files = {
        "TraitValues": (
            registry.dry_root / "Processed" / "Traits" / "External"
            / "Property_External.parquet",
            registry.dry_root / "Processed" / "Traits" / "Generated"
            / "Property_Generated.parquet",
        ),
        "DeepMPPValues": (
            registry.dry_root / "Processed" / "Predictions" / "DeepMPP"
            / "DeepMPP_External.parquet",
            registry.dry_root / "Processed" / "Predictions" / "DeepMPP"
            / "DeepMPP_Generated.parquet",
        ),
        "ProbyValues": (
            registry.dry_root / "Processed" / "Predictions" / "Proby"
            / "Proby_External.parquet",
            registry.dry_root / "Processed" / "Predictions" / "Proby"
            / "Proby_Generated.parquet",
        ),
        "Tox21Values": (
            registry.dry_root / "Processed" / "Predictions" / "Tox21"
            / "Tox21_External.parquet",
            registry.dry_root / "Processed" / "Predictions" / "Tox21"
            / "Tox21_Generated.parquet",
        ),
    }
    created = []
    connection = registry.connect()
    try:
        for view_name, (external, generated) in view_files.items():
            if not external.is_file() or not generated.is_file():
                continue
            connection.execute(
                f"""
                CREATE OR REPLACE VIEW {view_name} AS
                SELECT 'external' AS source_class, *
                FROM read_parquet({_sql_literal(str(external))})
                UNION ALL BY NAME
                SELECT 'generated' AS source_class, *
                FROM read_parquet({_sql_literal(str(generated))})
                """
            )
            created.append(view_name)
    finally:
        connection.close()
    return created


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate BuExperimentData DryData")
    parser.add_argument(
        "phase", choices=("all", "molecules", "traits", "predictions", "views")
    )
    parser.add_argument(
        "--model", action="append", choices=tuple(PREDICTION_SCHEMAS),
        help="Limit prediction migration; may be repeated",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not BACKUP_DRY.is_dir():
        raise FileNotFoundError(f"Backup DryData not found: {BACKUP_DRY}")
    registry = DryRegistry()
    registry.initialize()
    seed_registry(registry)

    report: dict[str, Any] = {}
    if args.phase in ("all", "molecules"):
        report["molecules"] = migrate_molecules(registry)
    if args.phase in ("all", "traits"):
        report["traits"] = migrate_traits(registry)
    if args.phase in ("all", "predictions"):
        report["predictions"] = migrate_predictions(registry, args.model)
    report["views"] = refresh_views(registry)
    report["registry"] = registry.status()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
