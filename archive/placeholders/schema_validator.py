"""
Schema Validator — enforces frozen schema compliance.

Validates:
  - Every entity has exactly: id, geometry, semantic, manufacturing, dimensions, relationships
  - No legacy keys appear in output
  - No entity has empty semantic block
  - No entity has empty manufacturing block
  - No relationship spam (max relationships per entity)
  - No duplicate entities
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)

FROZEN_ENTITY_KEYS = {"id", "geometry", "semantic", "manufacturing", "dimensions", "relationships"}
FORBIDDEN_TOP_KEYS = {
    "geometry_semantics", "relationship_semantics", "feature_semantics",
    "manufacturing_semantics", "constraints", "ownership_metadata", "dimension_annotations",
}


class SchemaValidator:
    """Validate pipeline output against frozen schema rules."""

    def validate(self, output: dict) -> list[str]:
        """
        Validate a complete pipeline output document.

        Returns list of error messages. Empty list = valid.
        """
        raise NotImplementedError("Schema validation to be implemented")
