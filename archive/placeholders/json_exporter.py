"""
JSON Exporter — writes final dataset to disk.

Outputs the frozen schema:
{
    "entities": [],
    "feature_groups": [],
    "relative_geometry": {},
    "bounding_box": {},
    "drawing_statistics": {}
}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class JSONExporter:
    """Export pipeline results as JSON."""

    def export(self, data: dict[str, Any], output_path: str | Path) -> None:
        """Write dataset record to JSON file."""
        raise NotImplementedError("JSON export to be implemented")
