"""
DXF Entity Reader — Stage 1 of the extraction pipeline.

Responsibilities:
  - Open DXF file (with recovery fallback)
  - Walk modelspace and explode INSERTs
  - Extract raw entity attributes into flat dicts
  - Return structured extraction result with metadata

Does NOT:
  - Filter entities
  - Classify roles
  - Detect features
  - Build relationships
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class DXFReader:
    """Read raw entities from a DXF file."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.supported_types = set(self.config.get("supported_entity_types", [
            "LINE", "CIRCLE", "ARC", "ELLIPSE", "LWPOLYLINE", "POLYLINE",
            "TEXT", "MTEXT", "DIMENSION", "INSERT", "LEADER", "POINT", "SPLINE",
        ]))

    def read(self, file_path: str | Path) -> dict[str, Any]:
        """
        Extract all supported entities from a DXF file.

        Returns:
            {
                "entities": list[dict],
                "metadata": {
                    "file": str,
                    "recovery_used": bool,
                    "warnings": list[str],
                    "skipped_count": int,
                }
            }
        """
        raise NotImplementedError("DXF reading logic to be implemented")
