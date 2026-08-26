# Stage 10 test and benchmark guide

The suite is split into three layers:

- `unit/` validates pure contracts, search request rules, and the documented job
  state-transition policy.
- `integration/` uses a temporary DuckDB database for migrations, previews,
  transactional imports, rollback, queries, jobs, and HTTP adapters.
- `performance/` runs the real service layer against generated large Parquet
  files. It is skipped unless explicitly enabled.

## Required scenario coverage

| Scenario | Primary coverage |
| --- | --- |
| Duplicate Molecules import | `integration/test_molecule_import.py` |
| Duplicate Annotation Package import | `integration/test_annotation_preview.py` |
| Attribute and Entry conflicts | `integration/test_annotation_preview.py` |
| Annotation value type error | `integration/test_annotation_preview.py` |
| Missing Molecule | `integration/test_annotation_preview.py` |
| Mid-transaction failure and rollback | Molecule and Annotation integration tests |
| File or package hash changed | Molecule and Annotation integration tests |
| Illegal Property modification | `integration/test_catalog_services.py` |
| Multi-condition query correctness | `integration/test_catalog_services.py` |
| Low-memory large-file import | `performance/test_stage10_benchmark.py` |

## Commands

From `backend/`, run the ordinary suite with:

```powershell
python -m pytest
```

The performance test defaults to one million Molecules, two million
Annotations, a 512 MB DuckDB memory limit, one DuckDB worker thread, and seven
repeated cross-queries. The 512 MB floor is empirical: this workload does not
complete at 256 MB on DuckDB 1.5.5 because the two-million-row Annotation
deduplication metric needs another 32 MB allocation near the limit.

```powershell
python -m pytest tests/performance --run-performance -s
```

Scale and memory can be changed without editing the test:

```powershell
$env:MLD_BENCH_MOLECULE_ROWS = "2000000"
$env:MLD_BENCH_MEMORY_LIMIT = "192MB"
python -m pytest tests/performance --run-performance -s
```

For a reusable JSON report, run the standalone benchmark. Its temporary
database is removed after completion unless `--work-directory` is supplied.

```powershell
python -m benchmarks.stage10 --output stage10-benchmark.json
```
