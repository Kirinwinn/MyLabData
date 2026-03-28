"""Convert business module.

Purpose:
- Consume strict JSON only.
- Export to markdown and CSV.
"""

from __future__ import annotations

from typing import Any, Dict


def to_markdown(strict_json: Dict[str, Any]) -> str:
    """Convert strict JSON to markdown string."""
    # TODO: Implement markdown rendering based on strict schema.
    return "# Report\n\nGenerated from strict JSON.\n"


def to_csv_bundle(strict_json: Dict[str, Any]) -> Dict[str, str]:
    """Convert strict JSON to CSV outputs.

    Returns:
        Mapping of filename -> CSV content.
    """
    # TODO: Implement CSV flattening rules and table export.
    return {
        "summary.csv": "key,value\nstatus,draft\n",
    }
