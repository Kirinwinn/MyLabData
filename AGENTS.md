# Repository Guide

## Commands

- Run commands from the repository root; imports assume the root is on `sys.path`.
- Use the Conda environment from `environment.yml`: `conda run -n MyLabData python ...`. The system Python may not have DuckDB/RDKit.
- Run all tests with `conda run -n MyLabData python -m unittest discover -s tests -v`.
- Run one test with `conda run -n MyLabData python -m unittest tests.test_dry_registry.DryRegistryTests.test_molecule_import_deduplicates_and_audits -v`.
- Start the Flask app with `conda run -n MyLabData python launch.py`; it defaults to `http://127.0.0.1:8501`. `APP_PORT`, `APP_DEBUG`, `APP_AUTO_REFRESH_ON_STARTUP`, and `APP_PRELOAD_STRUCTURES_ON_STARTUP` control startup behavior.
- There is no configured formatter, linter, type checker, or CI workflow; the unittest suite is the only automated verification currently in the repo.

## Architecture

- `launch.py` is the runtime entrypoint; `App/app.py` owns Flask routes, while `Search/` contains the Wet/Dry query and packaging logic used by those routes.
- Do not conflate the two Dry stores. The web app uses legacy SQLite `Database/Dry/Dry.db` plus `Separate/`, `Property/`, and `Prediction/` Parquets. `Database/Dry/Registry.py` is a separate MLD2 DuckDB registry at `DryData/Registry/DryData.duckdb`; it is not wired into the Flask app.
- Wet indexing writes SQLite `Database/Wet/Wet.db`; parsing and validation live under `Database/Tools/Wet/`. Wet names are data contracts, documented in `Supporting/MLD湿实验识别符.md`.
- The MLD2 schema source is `Database/Dry/schema_v1.sql`. Registry values remain in processed Parquets; DuckDB stores identities, provenance, import audits, caches, and lazy views.

## Data Safety

- Despite README claims, the legacy Flask pipelines do not read `DRY_DATA_ROOT` or `WET_DATA_ROOT` from the environment. Their defaults are hardcoded in `Database/Dry/Dry_Pipeline.py` and `Database/Wet/Wet_Pipeline.py`. Pass explicit `dry_root`/`db_path` or `data_root`/`db_path` arguments in tests and scripts rather than touching those defaults.
- Dry refresh only discovers files named exactly `BatchE###.parquet` or `BatchG###.parquet`. A matching Property file is optional; SMILES misalignment is reported as a warning and does not stop registration.
- MLD2 CLI commands default to `~/Documents/ExperiData/DryData` and mutate its DuckDB/workflow tree. Set `EXPERIDATA_ROOT` before CLI work; `Registry_CLI --db` overrides only the database path, not the workflow root. In tests, construct `DryRegistry` with both isolated `db_path` and `dry_root` values.
- `Database.Dry.Migrate_Backup` reads `BU_EXPERIMENT_DATA_ROOT` (default `~/Documents/BuExperimentData` on this machine) and writes the MLD2 root. Its verification expects original source files and all four lazy views to exist; do not use migration as a lightweight unit-test setup.
- Keep tests isolated with temporary directories, as in `tests/test_dry_registry.py`; data/database formats (`*.csv`, `*.xlsx`, `*.db`, etc.) are ignored by Git and can otherwise hide local side effects.
