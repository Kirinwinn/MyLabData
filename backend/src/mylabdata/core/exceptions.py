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


class MigrationError(DatabaseError):
    """Raised when schema migration discovery or execution fails."""


class MigrationChecksumError(MigrationError):
    """Raised when an applied migration file has been modified."""


class MigrationHistoryError(MigrationError):
    """Raised when migration files do not match the recorded history."""


class MoleculeFileError(ValidationError):
    """Raised when a Molecules input file violates the file contract."""


class MoleculeImportError(MyLabDataError):
    """Raised when a Molecules import transaction fails."""


class AnnotationPackageError(ValidationError):
    """Raised when an Annotation Package cannot be safely inspected."""


class PreviewTokenError(ValidationError):
    """Raised when a preview token no longer identifies the current package."""


class AnnotationImportError(MyLabDataError):
    """Raised after an Annotation import transaction is rolled back."""
