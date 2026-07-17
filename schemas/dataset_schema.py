"""Pydantic schema for the complete dataset output document."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.semantic_schema import SemanticEntity


class FeatureGroup(BaseModel):
    """Multi-entity feature group (counterbores, bolt patterns, etc.)."""
    feature_id: str
    feature_type: str
    source_entities: list[int]
    manufacturing: str


class DatasetRecord(BaseModel):
    """
    Complete output document for one DXF file.
    
    This is the FINAL output schema. No legacy keys allowed.
    """

    entities: list[SemanticEntity] = Field(default_factory=list)
    feature_groups: list[FeatureGroup] = Field(default_factory=list)
    relative_geometry: dict[str, Any] = Field(default_factory=dict)
    bounding_box: dict[str, Any] = Field(default_factory=dict)
    drawing_statistics: dict[str, Any] = Field(default_factory=dict)
