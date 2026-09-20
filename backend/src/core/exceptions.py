"""Application-level exception hierarchy."""


class MyLabDataError(Exception):
    """Base exception for expected MyLabData application failures."""


class ConfigurationError(MyLabDataError):
    """Raised when application configuration is invalid."""


class ValidationError(MyLabDataError):
    """Raised when an input package or request is invalid."""


class ConflictError(MyLabDataError):
    """Raised when incoming data conflicts with stored definitions."""


class DatabaseError(MyLabDataError):
    """Base exception for database infrastructure failures."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a DuckDB connection cannot be opened or configured."""
