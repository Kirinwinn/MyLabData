# MyLabData

MyLabData v2 is a molecule-centered data management application. The new version will use FastAPI for the backend, React and TypeScript for the frontend, and DuckDB as the primary DryData database.

## Current status

The backend skeleton, DuckDB infrastructure, initial business schema, Molecules
import, and non-mutating Annotation Package preview are present. Annotation
Packages are structurally validated, compared with the Attribute/Entry catalog,
and protected by a content-bound preview token. A persistent in-process job
coordinator now runs registered validation and import operations on one worker
thread and reports status through HTTP or SSE. Annotation Packages can now be
confirmed by preview token and imported in one transaction. Search services and
mutable Property operations are now implemented as HTTP-independent Services;
Property writes use the single background writer and retain an immutable change
history.

## Planned backend layers

- `core`: shared configuration, logging, and application exceptions.
- `db`: DuckDB connections, migrations, transactions, and SQL access.
- `schemas`: validated application and API data structures.
- `services`: import, search, catalog, property, and statistics workflows.
- `jobs`: background job coordination and progress events.
- `api`: FastAPI HTTP routing.

Runtime DryData is external to this repository and will be located through `MLD_DATA_ROOT`.
