# Specs Overview

This folder stores schema and style-spec files for the lightweight pipeline:

- `Search.py` output must validate against `scan_schema.process_conclusion.v1.json`.
- `Arrangement.py` output must validate against `strict_schema.common.v1.json`.
- `Arrangement.py` should also load one style spec file from this folder.
- `Convert.py` only accepts strict JSON (already validated).

Design constraints for your use case:

- Focus on experiment process and final conclusion images.
- Do not include detailed raw result dumps.
- Keep output concise and structured.

Suggested use:

1. Pick one `style_spec.*.v1.json` by experiment type.
2. Run `Search.py` to generate scan JSON.
3. Run `Arrangement.py` with scan JSON + style spec.
4. Validate strict JSON with `strict_schema.common.v1.json`.
5. Run `Convert.py` to export CSV and Markdown.
