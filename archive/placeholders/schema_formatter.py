"""
Schema Formatter — converts enriched entities into frozen output schema.

Output entity format (LOCKED):
{
    "id": int,
    "geometry": {},
    "semantic": {},
    "manufacturing": {},
    "dimensions": [],
    "relationships": []
}

No other format is permitted.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class SchemaFormatter:
    """Format enriched entities into the frozen output schema."""

    def format(self, entities: list[dict]) -> list[dict]:
        """Return list of frozen-schema entities."""
        raise NotImplementedError("Schema formatting to be implemented")
