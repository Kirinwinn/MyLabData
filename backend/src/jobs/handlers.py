"""Adapters between Job work orders and the currently available workflows."""

from datetime import UTC, datetime
from typing import Any

from access.molecules import EntryResultFilter
from jobs.manager import JobContext, JobManager, JobOutcome
from jobs.schemas import SEARCH_EXPORT_JOB_TYPE, SMILES_EXPORT_JOB_TYPE
from schemas.builder import PackageBuildRequest
from schemas.catalog import PropertyUpdateRequest, SearchRequest
from services.commands import DryDataCommands
from services.queries import DryDataQueries


def register_builtin_handlers(manager: JobManager) -> None:
    """Register all currently exposed business operations as Jobs."""
    manager.register("imports_query", _imports_query, job_kind="query")
    manager.register("import_query", _import_query, job_kind="query")
    manager.register("molecules_query", _molecules_query, job_kind="query")
    manager.register("molecule_query", _molecule_query, job_kind="query")
    manager.register("molecule_structure_3d_query", _molecule_structure_3d_query, job_kind="query")
    manager.register("molecule_attributes_query", _molecule_attributes_query, job_kind="query")
    manager.register(
        "molecule_attribute_annotations_query",
        _molecule_attribute_annotations_query,
        job_kind="query",
    )
    manager.register("attributes_query", _attributes_query, job_kind="query")
    manager.register("entries_query", _entries_query, job_kind="query")
    manager.register("entries_index_query", _entries_index_query, job_kind="query")
    manager.register("attribute_statistics_query", _attribute_statistics_query, job_kind="query")
    manager.register(
        "attribute_statistics_preheat", _attribute_statistics_preheat, job_kind="query"
    )
    manager.register("search_query", _search_query, job_kind="query")
    manager.register(SEARCH_EXPORT_JOB_TYPE, _search_export, job_kind="query")
    manager.register(SMILES_EXPORT_JOB_TYPE, _smiles_export, job_kind="query")
    manager.register("database_statistics_query", _database_statistics_query, job_kind="query")
    manager.register("packages_query", _packages_query, job_kind="query")
    manager.register("package_query", _package_query, job_kind="query")
    manager.register("package_preview", _package_preview, job_kind="query")
    manager.register("package_import", _package_import, job_kind="command")
    manager.register("package_build", _package_build, job_kind="command")
    manager.register("property_update", _property_update, job_kind="command")


def _imports_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading import records")
    records = DryDataQueries(context.manager.settings).list_imports(
        limit=_integer(payload, "limit", default=100),
        offset=_integer(payload, "offset", default=0),
    )
    return _items_outcome(records, "Import records read")


def _import_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading import record")
    record = DryDataQueries(context.manager.settings).get_import(_integer(payload, "import_id"))
    return _model_outcome(record, "Import record read")


def _molecules_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading molecule records")
    query = payload.get("query")
    if query is not None and not isinstance(query, str):
        raise ValueError("payload.query must be a string or null")
    result = DryDataQueries(context.manager.settings).list_molecules(
        query=query,
        limit=_integer(payload, "limit", default=100),
        offset=_integer(payload, "offset", default=0),
        entry_filter=_entry_result_filter(payload),
    )
    return JobOutcome(
        result={
            "items": [record.model_dump(mode="json") for record in result.items],
            "total": result.total,
        },
        message="Molecule records read",
    )


def _molecule_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading molecule record")
    record = DryDataQueries(context.manager.settings).get_molecule(_integer(payload, "molecule_id"))
    return _model_outcome(record, "Molecule record read")


def _molecule_structure_3d_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Generating temporary 3D structure")
    record = DryDataQueries(context.manager.settings).get_molecule_3d_structure(
        _integer(payload, "molecule_id")
    )
    return _model_outcome(record, "Temporary 3D structure generated")


def _molecule_attributes_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading molecule attributes")
    records = DryDataQueries(context.manager.settings).list_molecule_attributes(
        _integer(payload, "molecule_id")
    )
    return _items_outcome(records, "Molecule attributes read")


def _molecule_attribute_annotations_query(
    context: JobContext, payload: dict[str, Any]
) -> JobOutcome:
    context.set_status("running", 0.2, "Reading molecule annotations")
    records = DryDataQueries(context.manager.settings).list_molecule_attribute_annotations(
        _integer(payload, "molecule_id"),
        _integer(payload, "attribute_id"),
    )
    return _items_outcome(records, "Molecule annotations read")


def _attributes_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    del payload
    context.set_status("running", 0.2, "Reading attributes")
    return _items_outcome(
        DryDataQueries(context.manager.settings).list_attributes(), "Attributes read"
    )


def _entries_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading attribute entries")
    records = DryDataQueries(context.manager.settings).list_entries(
        _integer(payload, "attribute_id")
    )
    return _items_outcome(records, "Attribute entries read")


def _entries_index_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    del payload
    context.set_status("running", 0.2, "Reading entry index")
    return _items_outcome(
        DryDataQueries(context.manager.settings).list_entries_index(), "Entry index read"
    )


def _attribute_statistics_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Calculating attribute statistics")
    records = DryDataQueries(context.manager.settings).attribute_statistics(
        _integer(payload, "attribute_id")
    )
    return _items_outcome(records, "Attribute statistics calculated")


def _attribute_statistics_preheat(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    del payload
    context.set_status("running", 0.05, "Preheating attribute statistics cache")
    queries = DryDataQueries(context.manager.settings)

    def progress(done: int, total: int, name: str) -> None:
        fraction = 0.05 + 0.9 * (done / total) if total else 0.95
        context.set_status("running", fraction, f"Preheating statistics {done}/{total}: {name}")

    result = queries.preheat_attribute_statistics(progress=progress)
    return _model_outcome(result, "Attribute statistics preheat completed")


def _search_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.15, "Searching molecules")
    request = SearchRequest.model_validate(payload)
    result = DryDataQueries(context.manager.settings).search(request)
    return _model_outcome(result, "Molecule search completed")


def _search_export(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("validating", 0.1, "Validating search export request")
    request = SearchRequest.model_validate(payload)
    context.raise_if_cancelled()
    context.set_status("running", 0.4, "Running search and writing export workbook")
    result = DryDataQueries(context.manager.settings).export_search_workbook(
        request,
        file_stem=_export_file_stem(context.job_id),
    )
    return JobOutcome(result=result.model_dump(mode="json"), message="Search export completed")


def _smiles_export(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    rows_per_file = _integer(payload, "rows_per_file", default=50_000)
    if rows_per_file < 1:
        raise ValueError("payload.rows_per_file must be a positive integer")
    context.set_status("running", 0.2, "Writing chunked SMILES CSV archive")
    result = DryDataQueries(context.manager.settings).export_smiles_archive(
        rows_per_file=rows_per_file,
        file_stem=_export_file_stem(context.job_id, prefix="smiles_export"),
        entry_filter=_entry_result_filter(payload),
    )
    return JobOutcome(result=result.model_dump(mode="json"), message="SMILES export completed")


def _export_file_stem(job_id: str, *, prefix: str = "search_export") -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{timestamp}_{job_id[:8]}"


def _database_statistics_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    del payload
    context.set_status("running", 0.2, "Calculating database statistics")
    statistics = DryDataQueries(context.manager.settings).database_statistics(
        jobs=context.manager.repository.count()
    )
    return _model_outcome(statistics, "Database statistics calculated")


def _packages_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    del payload
    context.set_status("running", 0.2, "Scanning incoming packages")
    return _items_outcome(
        DryDataQueries(context.manager.settings).list_packages(), "Incoming packages scanned"
    )


def _package_query(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("running", 0.2, "Reading package details")
    package_id = _package_id(payload)
    detail = DryDataQueries(context.manager.settings).get_package(package_id)
    return _model_outcome(detail, "Package details read")


def _package_preview(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    package_id = _package_id(payload)
    context.set_status("running", 0.2, "Validating package")
    preview = DryDataQueries(context.manager.settings).preview_package(package_id)
    if isinstance(preview, dict):
        return JobOutcome(result=preview, message="Molecules preview completed")
    if preview.errors:
        raise ValueError("; ".join(preview.errors))
    return JobOutcome(
        result=preview.model_dump(mode="json"),
        status="waiting_confirmation",
        message="Annotation Package is ready for confirmation",
    )


def _package_import(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    package_id = _package_id(payload)
    preview_token = payload.get("preview_token")
    if preview_token is not None and not isinstance(preview_token, str):
        raise ValueError("payload.preview_token must be a string")
    context.set_status("validating", 0.15, "Validating import package")
    context.raise_if_cancelled()
    context.set_status("importing", 0.5, "Importing package into DryData")
    result, archived = DryDataCommands(context.manager.settings).import_package(
        package_id,
        preview_token=preview_token,
    )
    result_payload = {
        "import_id": result.import_id,
        "package_name": result.package_name,
        "package_hash": result.package_hash,
        "total_rows": result.total_rows,
        "inserted_rows": result.inserted_rows,
        "existing_rows": result.existing_rows,
        "duplicate_rows": result.duplicate_rows,
        "invalid_rows": result.invalid_rows,
        "created_attributes": result.created_attributes,
        "created_entries": result.created_entries,
        "created_sources": result.created_sources,
        "archived": archived,
    }
    if not archived:
        context.set_status("archiving", 0.9, "Database committed; package archive pending")
        return JobOutcome(
            result=result_payload,
            status="archive_pending",
            message="Database committed; package archive needs retry",
        )
    context.set_status("archiving", 0.9, "Archiving imported package")
    return JobOutcome(result=result_payload, message="Package import completed")


def _package_id(payload: dict[str, Any]) -> str:
    package_id = payload.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        raise ValueError("payload.package_id must be a non-empty string")
    return package_id


def _package_build(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    context.set_status("validating", 0.1, "Validating package build request")
    request = PackageBuildRequest.model_validate(payload)
    context.raise_if_cancelled()
    context.set_status("running", 0.4, "Composing the Annotation Package")
    result = DryDataCommands(context.manager.settings).build_annotation_package(request)
    message = "Package build preview computed" if result.dry_run else "Annotation Package built"
    return JobOutcome(result=result.model_dump(mode="json"), message=message)


def _property_update(context: JobContext, payload: dict[str, Any]) -> JobOutcome:
    try:
        molecule_id = int(payload["molecule_id"])
        entry_id = int(payload["entry_id"])
        request = PropertyUpdateRequest.model_validate(payload["request"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid property update Job payload") from exc
    context.set_status("importing", 0.5, "Updating mutable Property")
    result = DryDataCommands(context.manager.settings).update_property(
        molecule_id,
        entry_id,
        request,
    )
    return JobOutcome(result=result.model_dump(mode="json"), message="Property update completed")


def _entry_result_filter(payload: dict[str, Any]) -> EntryResultFilter | None:
    raw = payload.get("entry_filter")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("payload.entry_filter must be an object")
    return EntryResultFilter(
        entry_id=_integer(raw, "entry_id"),
        has_results=_boolean(raw, "has_results"),
    )


def _boolean(payload: dict[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"payload.{name} must be a boolean")
    return value


def _integer(payload: dict[str, Any], name: str, *, default: int | None = None) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"payload.{name} must be an integer")
    return value


def _items_outcome(records: list[Any], message: str) -> JobOutcome:
    return JobOutcome(
        result={"items": [record.model_dump(mode="json") for record in records]},
        message=message,
    )


def _model_outcome(record: Any, message: str) -> JobOutcome:
    return JobOutcome(result=record.model_dump(mode="json"), message=message)
