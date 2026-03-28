"""Arrangement business module.

Purpose:
- Consume scan JSON + style spec.
- Produce strict JSON according to target schema.
"""

from __future__ import annotations

from typing import Any, Dict


def arrange(scan_json: Dict[str, Any], style_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Arrange scan data into strict JSON format.

    Args:
        scan_json: Raw scan JSON from Search.py.
        style_spec: Style/specification JSON.

    Returns:
        Strict JSON dictionary.
    """
    # TODO: Implement LM Studio (Gemma) orchestration and schema validation.
    return {
        "version": "0.1.0",
        "status": "draft",
        "style": style_spec,
        "content": {},
        "source_meta": {
            "source_count": int(scan_json.get("source_count", 0)),
        },
    }
