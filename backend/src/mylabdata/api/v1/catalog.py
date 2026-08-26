"""HTTP serialization layer for existing read-only catalog services."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from mylabdata.api.dependencies import get_app_settings, get_job_manager
from mylabdata.core.config import Settings
from mylabdata.jobs.manager import JobManager
from mylabdata.schemas.catalog import (
    AttributeRecord,
    AttributeStatistics,
    DatabaseStats,
    EntryRecord,
    ImportRecord,
    MoleculeDetail,
    MoleculeSummary,
    PropertyUpdateRequest,
    SearchRequest,
    SearchResult,
)
from mylabdata.schemas.jobs import JobAccepted
from mylabdata.services.catalog_reader import (
    read_attribute_statistics,
    read_attributes,
    read_entries,
    read_import,
    read_imports,
    read_molecule,
    read_molecules,
    read_stats,
)
from mylabdata.services.search import search_molecules as execute_search

router = APIRouter()
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
ManagerDependency = Annotated[JobManager, Depends(get_job_manager)]


@router.get("/imports", response_model=list[ImportRecord], tags=["imports"])
def list_imports(
    settings: SettingsDependency,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ImportRecord]:
    return read_imports(settings, limit=limit, offset=offset)


@router.get("/imports/{import_id}", response_model=ImportRecord, tags=["imports"])
def get_import(import_id: int, settings: SettingsDependency) -> ImportRecord:
    try:
        return read_import(settings, import_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Import not found") from exc


@router.get("/molecules", response_model=list[MoleculeSummary], tags=["molecules"])
def list_molecules(
    settings: SettingsDependency,
    query: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[MoleculeSummary]:
    return read_molecules(settings, query=query, limit=limit, offset=offset)


@router.get("/molecules/{molecule_id}", response_model=MoleculeDetail, tags=["molecules"])
def get_molecule(molecule_id: int, settings: SettingsDependency) -> MoleculeDetail:
    try:
        return read_molecule(settings, molecule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Molecule not found") from exc


@router.get("/attributes", response_model=list[AttributeRecord], tags=["attributes"])
def list_attributes(settings: SettingsDependency) -> list[AttributeRecord]:
    return read_attributes(settings)


@router.get(
    "/attributes/{attribute_id}/entries",
    response_model=list[EntryRecord],
    tags=["attributes"],
)
def list_attribute_entries(
    attribute_id: int,
    settings: SettingsDependency,
) -> list[EntryRecord]:
    try:
        return read_entries(settings, attribute_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attribute not found") from exc


@router.get(
    "/attributes/{attribute_id}/stats",
    response_model=list[AttributeStatistics],
    tags=["attributes"],
)
def get_attribute_statistics(
    attribute_id: int,
    settings: SettingsDependency,
) -> list[AttributeStatistics]:
    try:
        return read_attribute_statistics(settings, attribute_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Attribute not found") from exc


@router.post("/search", response_model=SearchResult, tags=["search"])
def search_molecules(
    request: SearchRequest,
    settings: SettingsDependency,
) -> SearchResult:
    return execute_search(request, settings)


@router.put(
    "/molecules/{molecule_id}/properties/{entry_id}",
    response_model=JobAccepted,
    status_code=202,
    tags=["properties"],
)
def update_property(
    molecule_id: int,
    entry_id: int,
    request: PropertyUpdateRequest,
    manager: ManagerDependency,
) -> JobAccepted:
    job = manager.submit(
        "property_update",
        {
            "molecule_id": molecule_id,
            "entry_id": entry_id,
            "request": request.model_dump(mode="json"),
        },
    )
    return JobAccepted(job_id=job.job_id)


@router.get("/stats", response_model=DatabaseStats, tags=["stats"])
def get_stats(settings: SettingsDependency) -> DatabaseStats:
    return read_stats(settings)
