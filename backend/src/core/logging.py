"""Backend logging configuration."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure a small, process-wide logging baseline."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
