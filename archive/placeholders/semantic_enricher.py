"""
Semantic Enricher — merges features/manufacturing into entities.

Ensures every entity has:
  - semantic block (feature_type + engineering_role)
  - manufacturing block (process + feasibility)
  - dimensions list
  - relationships list

No entity is allowed to remain as anonymous raw geometry.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class SemanticEnricher:
    """Enrich entities with semantic and manufacturing meaning."""

    def enrich(self, entities: list[dict], features: list[dict]) -> None:
        """Mutate entities in-place: attach semantic + manufacturing blocks."""
        raise NotImplementedError("Semantic enrichment to be implemented")
