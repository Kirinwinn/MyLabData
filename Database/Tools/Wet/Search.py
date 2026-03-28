"""Search business module.

Purpose:
- Scan source files (primarily images) and extract raw structured data.
- Output scan JSON only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def scan_files(file_paths: List[str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Scan input files and return scan JSON.

    Args:
        file_paths: Input file paths to scan.
        options: Optional scanner settings.

    Returns:
        A scan JSON dictionary.
    """
    # TODO: Implement OCR/layout/table extraction pipeline.
    return {
        "version": "0.1.0",
        "source_count": len(file_paths),
        "records": [],
        "meta": {
            "options": options or {},
        },
    }
