"""Command-line interface for the MLD2 DryData registry."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .Registry import DryRegistry


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the MyLabData MLD2 registry")
    parser.add_argument("--db", help="Override DryData.duckdb path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create directories and initialize schema")
    subparsers.add_parser("status", help="Show registry row counts")

    source = subparsers.add_parser("add-source", help="Register a source")
    source.add_argument("source_key")
    source.add_argument("source_name")
    source.add_argument("source_type")
    source.add_argument("--uri")
    source.add_argument("--description")

    attribute = subparsers.add_parser("add-attribute", help="Register an attribute")
    attribute.add_argument("attribute_key")
    attribute.add_argument("attribute_name")
    attribute.add_argument("attribute_category")
    attribute.add_argument("value_type")
    attribute.add_argument("--unit")
    attribute.add_argument("--model-name")
    attribute.add_argument("--model-version")

    molecules = subparsers.add_parser(
        "import-molecules", help="Import prepared molecules from CSV or Parquet"
    )
    molecules.add_argument("file_path")
    molecules.add_argument("source_key")
    molecules.add_argument("source_name")
    molecules.add_argument("source_type")
    molecules.add_argument("--source-class")
    molecules.add_argument("--skip-checksum", action="store_true")

    attribute_file = subparsers.add_parser(
        "register-file", help="Register a processed trait/prediction/annotation file"
    )
    attribute_file.add_argument("file_path")
    attribute_file.add_argument("source_key")
    attribute_file.add_argument("source_name")
    attribute_file.add_argument("source_type")
    attribute_file.add_argument("attribute_category")
    attribute_file.add_argument("attribute_prefix")
    attribute_file.add_argument("--source-class")
    attribute_file.add_argument("--model-name")
    attribute_file.add_argument("--exclude", action="append", default=[])
    attribute_file.add_argument("--skip-checksum", action="store_true")
    attribute_file.add_argument(
        "--trusted-identities",
        action="store_true",
        help="Skip registry reconciliation for a file already joined to Molecules",
    )

    search = subparsers.add_parser("search", help="Search registered molecules")
    search.add_argument("query", nargs="?")
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--offset", type=int, default=0)

    imports = subparsers.add_parser("imports", help="List recent imports")
    imports.add_argument("--limit", type=int, default=100)
    subparsers.add_parser("seed", help="Register built-in traits and model attributes")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    registry = DryRegistry(db_path=args.db) if args.db else DryRegistry()

    if args.command == "init":
        _print({"database": str(registry.initialize()), "status": "ready"})
    elif args.command == "status":
        _print(registry.status())
    elif args.command == "add-source":
        source_id = registry.register_source(
            args.source_key,
            args.source_name,
            args.source_type,
            source_uri=args.uri,
            description=args.description,
        )
        _print({"source_id": source_id})
    elif args.command == "add-attribute":
        attribute_id = registry.register_attribute(
            args.attribute_key,
            args.attribute_name,
            args.attribute_category,
            args.value_type,
            unit=args.unit,
            model_name=args.model_name,
            model_version=args.model_version,
        )
        _print({"attribute_id": attribute_id})
    elif args.command == "import-molecules":
        _print(registry.import_molecules(
            args.file_path,
            source_key=args.source_key,
            source_name=args.source_name,
            source_type=args.source_type,
            source_class=args.source_class,
            calculate_checksum=not args.skip_checksum,
        ))
    elif args.command == "register-file":
        _print(registry.register_attribute_file(
            args.file_path,
            source_key=args.source_key,
            source_name=args.source_name,
            source_type=args.source_type,
            attribute_category=args.attribute_category,
            attribute_prefix=args.attribute_prefix,
            source_class=args.source_class,
            model_name=args.model_name,
            exclude_columns=args.exclude,
            calculate_checksum=not args.skip_checksum,
            validate_identities=not args.trusted_identities,
        ))
    elif args.command == "search":
        _print(registry.search_molecules(
            args.query, limit=args.limit, offset=args.offset
        ))
    elif args.command == "imports":
        _print(registry.list_imports(limit=args.limit))
    elif args.command == "seed":
        from .Registry_Seed import seed_registry
        _print(seed_registry(registry))


if __name__ == "__main__":
    main()
