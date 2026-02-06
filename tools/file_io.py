"""File I/O tools for reading and writing state files."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# All file operations are relative to the output directory
OUTPUT_DIR = Path("output")

FILE_READ_TOOL = {
    "name": "file_read",
    "description": (
        "Read a file from the output directory. Use this to read research_state.json, "
        "model_state.json, or any other file produced during the pipeline."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename to read (relative to output/). e.g., 'research_state.json'",
            },
        },
        "required": ["filename"],
    },
}

FILE_WRITE_TOOL = {
    "name": "file_write",
    "description": (
        "Write content to a file in the output directory. Use this to create or update "
        "research_state.json, model_state.json, or other output files. For JSON files, "
        "provide the content as a valid JSON string."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename to write (relative to output/). e.g., 'research_state.json'",
            },
            "content": {
                "type": "string",
                "description": "The content to write. For JSON files, this should be a valid JSON string.",
            },
        },
        "required": ["filename", "content"],
    },
}


def _resolve_path(filename: str) -> Path:
    """Resolve a filename to a safe path within the output directory."""
    # Prevent path traversal
    clean = Path(filename).name if "/" in filename or "\\" in filename else filename
    # Allow subdirectories within output
    if "/" in filename and not filename.startswith(".."):
        clean = filename
    path = OUTPUT_DIR / clean
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def execute_file_read(filename: str) -> str:
    """Read a file from the output directory."""
    try:
        path = _resolve_path(filename)
        if not path.exists():
            return json.dumps({"error": f"File not found: {filename}"})

        content = path.read_text(encoding="utf-8")

        # Validate JSON if it's a JSON file
        if path.suffix == ".json":
            try:
                parsed = json.loads(content)
                return json.dumps({
                    "filename": filename,
                    "content": parsed,
                }, indent=2)
            except json.JSONDecodeError:
                return json.dumps({
                    "filename": filename,
                    "content": content,
                    "warning": "File has .json extension but content is not valid JSON",
                })

        return json.dumps({
            "filename": filename,
            "content": content,
        })

    except Exception as e:
        logger.exception("File read failed")
        return json.dumps({"error": f"Read failed: {str(e)}"})


def execute_file_write(filename: str, content: str) -> str:
    """Write content to a file in the output directory."""
    try:
        path = _resolve_path(filename)

        # Validate JSON if writing a JSON file
        if path.suffix == ".json":
            try:
                parsed = json.loads(content)
                # Re-serialize with consistent formatting
                content = json.dumps(parsed, indent=2, ensure_ascii=False)
            except json.JSONDecodeError as e:
                return json.dumps({
                    "error": f"Invalid JSON content: {str(e)}",
                    "hint": "Ensure the content is valid JSON before writing to a .json file.",
                })

        path.write_text(content, encoding="utf-8")

        size = path.stat().st_size
        return json.dumps({
            "success": True,
            "filename": filename,
            "size_bytes": size,
        })

    except Exception as e:
        logger.exception("File write failed")
        return json.dumps({"error": f"Write failed: {str(e)}"})
