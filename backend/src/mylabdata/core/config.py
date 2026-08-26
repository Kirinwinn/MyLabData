"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MyLabData backend settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MLD_",
        extra="ignore",
    )

    data_root: Path
    database_path: Path | None = None
    temp_directory: Path | None = None
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    memory_limit: str = "3GB"
    threads: int = Field(default=4, ge=1)
    preserve_insertion_order: bool = False

    @property
    def resolved_database_path(self) -> Path:
        """Return the configured or default DuckDB database location."""
        return self.database_path or self.data_root / "Registry" / "mylabdata.duckdb"

    @property
    def resolved_temp_directory(self) -> Path:
        """Return the configured or default temporary data directory."""
        return self.temp_directory or self.data_root / "Temp"

    @property
    def incoming_molecules_directory(self) -> Path:
        """Return the directory scanned for molecule Parquet files."""
        return self.data_root / "Incoming" / "Molecules"

    @property
    def incoming_annotations_directory(self) -> Path:
        """Return the directory containing incoming Annotation Packages."""
        return self.data_root / "Incoming" / "Annotations"

    @property
    def processed_annotations_directory(self) -> Path:
        """Return the destination for committed Annotation Packages."""
        return self.data_root / "Processed" / "Annotations"

    @property
    def failed_annotations_directory(self) -> Path:
        """Return the destination for structurally invalid Annotation Packages."""
        return self.data_root / "Failed" / "Annotations"


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings."""
    return Settings()
