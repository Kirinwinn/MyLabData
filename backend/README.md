# MyLabData Backend

This directory contains the FastAPI backend package and its tests. The project
currently includes the application skeleton, DuckDB infrastructure, initial
business schema, and the Molecules Parquet import workflow. Molecule insertion
uses temporary tables and set-based `INSERT ... SELECT` statements rather than
Python row-by-row writes.

DuckDB migrations are stored in `src/mylabdata/db/migrations` and executed in
numeric order. The migration runner records each filename and SHA-256 checksum in
`_schema_migrations` so an applied migration cannot be silently changed.

The initial schema is defined by `001_initial.sql`. It creates `Molecules`,
`Attributes`, `Entries`, `Annotations`, `Sources`, `Imports`,
`AttributeDistributions`, and `AttributeStats`.

Molecules input files are discovered in `Incoming/Molecules`. A valid file must
be Parquet and contain a VARCHAR `canonical_smiles` column. Blank values are
reported as invalid; duplicates are removed by canonical SMILES before the
transactional insert. Every import attempt that reaches the database is tracked
in `Imports` with its SHA-256 file hash and outcome.
The audit also retains total, valid, new, existing, duplicate, inserted, and
invalid row counts.

Annotation Package preview accepts `annotation_manifest.json`,
`annotations.parquet`, `processing_report.json`, and an optional
`rejected.parquet`. It validates package structure, JSON contracts, Parquet
schema and row consistency, then compares Attribute, Entry, Molecule, and
Annotation keys through a read-only DuckDB connection. Preview does not register
definitions or import values. Its token is bound to the package name and a
deterministic SHA-256 hash, so later import code can reject changed packages.

Background operations are persisted in `Jobs` and executed by one in-process
worker thread. Package actions and Property updates return a job ID immediately;
state can be read from `/api/v1/jobs/{job_id}` or streamed from
`/api/v1/jobs/{job_id}/events`. The first version intentionally uses neither
Redis nor Celery. On startup, records left in a non-terminal state are marked
failed with an application-restart error instead of being reported as complete.

The versioned HTTP API exposes scanned packages, imports, jobs and SSE events,
molecules, Attributes and Entries, and database summary statistics under
`/api/v1`. Package actions accept only opaque IDs returned by `GET
/api/v1/packages`; the generic job-submission endpoint is intentionally not
public, so clients cannot submit filesystem paths. Annotation import requires a
current preview token and atomically registers catalog definitions, writes
values, records the import, and only then moves the package to `Processed`.
Multi-condition search validates operators against number, text, and boolean
value types and combines Entry predicates with `INTERSECT` or `UNION`. Mutable
Property updates run through the single writer and append old value, new value,
source, and timestamp to `PropertyChanges`.

Stage 10 divides verification into fast unit tests, temporary-DuckDB integration
tests, and an opt-in real-scale benchmark. The benchmark exercises the actual
Molecule and Annotation import services under a configurable DuckDB memory
limit, repeats a two-Entry intersection query, and reports throughput, query
latency, database size, temp spill, and peak process RSS as JSON. See
`tests/README.md` for the coverage matrix and commands.
