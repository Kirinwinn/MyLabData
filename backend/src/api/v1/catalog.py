"""HTTP endpoints that submit catalog Query and Command Jobs."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_job_manager
from jobs.manager import JobManager
from jobs.schemas import SEARCH_EXPORT_JOB_TYPE, SMILES_EXPORT_JOB_TYPE, JobAccepted
from schemas.catalog import (
    MoleculeListQueryRequest,
    PageQueryRequest,
    PropertyUpdateRequest,
    SearchRequest,
    SmilesExportRequest,
)

router = APIRouter()
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]


@router.post(
    "/imports/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["imports"],
)
def list_imports(request: PageQueryRequest, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "imports_query", request.model_dump(mode="json"))


@router.post(
    "/imports/{import_id}/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["imports"],
)
def get_import(import_id: int, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "import_query", {"import_id": import_id})


@router.post(
    "/molecules/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def list_molecules(
    request: MoleculeListQueryRequest,
    manager: ManagerDependency,
) -> JobAccepted:
    return _submit(manager, "molecules_query", request.model_dump(mode="json"))


@router.post(
    "/molecules/{molecule_id}/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def get_molecule(molecule_id: int, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "molecule_query", {"molecule_id": molecule_id})


@router.post(
    "/molecules/{molecule_id}/structure-3d/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def get_molecule_3d_structure(molecule_id: int, manager: ManagerDependency) -> JobAccepted:
    """Generate a 3D structure in memory; no result is persisted to DryData."""
    return _submit(manager, "molecule_structure_3d_query", {"molecule_id": molecule_id})


@router.post(
    "/molecules/{molecule_id}/attributes/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def list_molecule_attributes(molecule_id: int, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "molecule_attributes_query", {"molecule_id": molecule_id})


@router.post(
    "/molecules/{molecule_id}/attributes/{attribute_id}/annotations/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def list_molecule_attribute_annotations(
    molecule_id: int,
    attribute_id: int,
    manager: ManagerDependency,
) -> JobAccepted:
    return _submit(
        manager,
        "molecule_attribute_annotations_query",
        {"molecule_id": molecule_id, "attribute_id": attribute_id},
    )


@router.post(
    "/attributes/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["attributes"],
)
def list_attributes(manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "attributes_query", {})


@router.post(
    "/attributes/{attribute_id}/entries/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["attributes"],
)
def list_attribute_entries(attribute_id: int, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "entries_query", {"attribute_id": attribute_id})


@router.post(
    "/entries/index/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["attributes"],
)
def list_entries_index(manager: ManagerDependency) -> JobAccepted:
    """Submit an index of every registered entry with its attribute."""
    return _submit(manager, "entries_index_query", {})


@router.post(
    "/attributes/{attribute_id}/stats/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["attributes"],
)
def get_attribute_statistics(attribute_id: int, manager: ManagerDependency) -> JobAccepted:
    return _submit(
        manager,
        "attribute_statistics_query",
        {"attribute_id": attribute_id},
    )


@router.post(
    "/attributes/stats/preheat",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["attributes"],
)
def preheat_attribute_statistics(manager: ManagerDependency) -> JobAccepted:
    """Precompute and cache statistics for every Attribute."""
    return _submit(manager, "attribute_statistics_preheat", {})


@router.post(
    "/search",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["search"],
)
def search_molecules(request: SearchRequest, manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "search_query", request.model_dump(mode="json"))


@router.post(
    "/search/export",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["search"],
)
def export_search(request: SearchRequest, manager: ManagerDependency) -> JobAccepted:
    """Submit an XLSX workbook export for one full search result set."""
    return _submit(manager, SEARCH_EXPORT_JOB_TYPE, request.model_dump(mode="json"))


@router.post(
    "/molecules/smiles/export",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["molecules"],
)
def export_molecule_smiles(
    request: SmilesExportRequest,
    manager: ManagerDependency,
) -> JobAccepted:
    """Submit a chunked single-column SMILES CSV archive for the full registry."""
    return _submit(manager, SMILES_EXPORT_JOB_TYPE, request.model_dump(mode="json"))


@router.put(
    "/molecules/{molecule_id}/properties/{entry_id}",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["properties"],
)
def update_property(
    molecule_id: int,
    entry_id: int,
    request: PropertyUpdateRequest,
    manager: ManagerDependency,
) -> JobAccepted:
    return _submit(
        manager,
        "property_update",
        {
            "molecule_id": molecule_id,
            "entry_id": entry_id,
            "request": request.model_dump(mode="json"),
        },
    )


@router.post(
    "/stats/query",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["stats"],
)
def get_stats(manager: ManagerDependency) -> JobAccepted:
    return _submit(manager, "database_statistics_query", {})


def _submit(manager: JobManager, job_type: str, payload: dict[str, Any]) -> JobAccepted:
    try:
        job = manager.submit(job_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JobAccepted(job_id=job.job_id)
