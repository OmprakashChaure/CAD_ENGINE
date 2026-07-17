"""Pydantic schema for engineering features detected from geometry."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class EngineeringFeature(BaseModel):
    """An engineering feature inferred from one or more geometry entities."""

    feature_id: str
    feature_type: str = Field(description="drilled_hole, counterbore, slot, fillet, chamfer, etc.")
    source_entities: list[int] = Field(description="IDs of geometry entities composing this feature")
    manufacturing: str = Field(description="Primary manufacturing process")
    properties: dict[str, Any] = Field(default_factory=dict)
    pattern_group: Optional[dict[str, Any]] = None
