# DryData Naming and Status Specification

## 1. Top-level directories
Only the following top-level folders are used under `DryData/`:

- `External/`
- `Generated/`
- `Separate/`
- `Prediction/`
- `Property/`

`Generation/` is deprecated. Use only `Generated/`.

## 2. Batch naming
Batch base identifier format:

- `Batch[S][NNN]`

Where:

- `[S]` is source code:
- `E` for External
- `G` for Generated
- `[NNN]` is a 3-digit batch number, e.g. `001`, `078`, `120`

Examples:

- `BatchE001`
- `BatchE078`
- `BatchG004`

## 3. Status suffix semantics
The following suffixes are reserved:

- `RO` = Raw Origin
  - A folder containing source slices or source files before standardized processing.
- `RW` = Raw Working
  - A consolidated parquet file prepared from `RO` data for downstream processing.
- No suffix
  - The formal standardized batch used for core Dry workflows.

Examples:

- `External/BatchE001RO/`
- `External/BatchE001RW.parquet`
- `Separate/BatchE001.parquet`

## 4. Directory-specific file rules

### 4.1 `External/`
Required pattern per batch:

- `BatchEXXXRO/` (required)
- `BatchEXXXRW.parquet` (recommended once consolidation is complete)

Allowed file types inside `RO`:

- `xlsx`, `csv`, `sdf`, `parquet`

### 4.2 `Generated/`
Required pattern per batch:

- `BatchGXXXRO/` (required)
- `BatchGXXXRW.parquet` (recommended once consolidation is complete)

Allowed file types inside `RO`:

- `xlsx`, `csv`, `sdf`, `parquet`

### 4.3 `Separate/`
Required output:

- `Batch[S][NNN].parquet`

This is the canonical standardized SMILES dataset for each batch.

### 4.4 `Prediction/`
Model-level folder structure:

- `Prediction/[ModelName]/Batch[S][NNN]/`

Model naming rule:

- Folder name format is `[ModelName]` with first letter uppercase and remaining letters lowercase where applicable.
- Example: `Proby`

Slice naming rule (mandatory fixed width):

- `Batch[S][NNN]Slice[MMM].xlsx`
- `[MMM]` is a 3-digit index: `001`, `002`, `003`, ...

Examples:

- `BatchE002Slice001.xlsx`
- `BatchE002Slice044.xlsx`

### 4.5 `Property/`
Required output:

- `Batch[S][NNN].parquet`

Each file contains computed molecular features tied to the corresponding standardized batch.

## 5. Slice naming unification policy
Legacy names such as:

- `Slice1.xlsx`
- `Slice01.xlsx`
- `*_slice_0001_of_0043.xlsx`

should be phased out for new outputs.

All new slice files must follow:

- `Batch[S][NNN]Slice[MMM].xlsx`

## 6. Single ingest note policy
Only one global ingest note markdown file is maintained:

- `DryData/_IngestLog.md`

It records preprocessing and ingest context, for example:

- batch id and source
- preprocessing steps
- exceptions and manual fixes
- operator and timestamp

## 7. Duplicate-computation policy
Data storage and computation are separated:

- Batch data in `Separate/` remains batch-independent and complete.
- Computation should be deduplicated globally by canonical molecular identifier.

Recommended identifier priority:

1. `inchikey`
2. `canonical_smiles`

## 8. Suggested lifecycle states
Suggested processing states for tracking:

- `RO_READY`
- `RW_READY`
- `SEPARATED`
- `PREDICTED`
- `PROPERTY_DONE`
- `DB_SYNCED`

## 9. Effective date
This specification is effective immediately for all newly created Dry batches.
