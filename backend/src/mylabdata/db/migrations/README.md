# DuckDB migrations

Migration filenames use the following form:

```text
NNN_lowercase_name.sql
```

Examples include `001_initial.sql` and `002_add_import_status.sql`.

Rules:

1. Versions are numeric, unique, and applied in ascending order.
2. Applied files are immutable; their SHA-256 checksums are recorded in DuckDB.
3. Each file contains schema SQL only and must not contain its own `BEGIN`,
   `COMMIT`, or `ROLLBACK` statements.
4. The migration runner executes each file and its history record in one
   transaction.
5. A migration file must not be removed after it has been applied.

`001_initial.sql` defines the initial MyLabData business schema. Later migrations
add Molecules import metrics and persistent background job coordination.
`004_property_changes.sql` adds immutable audit history for mutable Properties.
