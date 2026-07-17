"""
Role Classifier — assigns engineering roles to entities.

Uses linetype, layer name, and entity context to determine:
  - visible_edge
  - hidden_line
  - centerline
  - construction_line
  - dimension
  - annotation
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class RoleClassifier:
    """Classify entity engineering role from DXF metadata."""

    def __init__(self, layer_rules: dict | None = None):
        self.layer_rules = layer_rules or {}

    def classify(self, entity: dict) -> str:
        """Return the engineering role for an entity."""
        raise NotImplementedError("Role classification to be implemented")
