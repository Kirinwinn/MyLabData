"""DuckDB infrastructure and schema migration management."""

from mylabdata.db.connection import connection, open_connection
from mylabdata.db.migrate import get_schema_version, migrate

__all__ = [
    "connection",
    "get_schema_version",
    "migrate",
    "open_connection",
]

