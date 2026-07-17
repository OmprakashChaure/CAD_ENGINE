"""
Canonical topology graph schema.

Defines the permanent topology contract for:
  - Shared vertices (geometric connection points)
  - Topology edges (entity-to-entity connectivity)
  - Topology graph container

All topology relationships are geometry-derived ONLY.
No semantic inference. No heuristic relationships.
"""
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field


class TopologyVertex(BaseModel):
    """
    A shared geometric vertex where entities connect.

    Represents a point in space where two or more entities
    share an endpoint (within epsilon tolerance).
    """

    vertex_id: str = Field(description="Stable vertex identifier: vtx_XXXXX")
    x: float
    y: float
    connected_entities: List[str] = Field(
        description="entity_ids sharing this vertex"
    )


class TopologyEdge(BaseModel):
    """
    A topology connection between two entities.

    Derived ONLY from shared vertices.
    NOT from distance heuristics or semantic inference.
    """

    source_entity_id: str
    target_entity_id: str
    shared_vertex_id: str = Field(
        description="The vertex where these entities connect"
    )


class TopologyGraph(BaseModel):
    """
    Complete topology graph for one drawing.

    Contains:
      - All shared vertices (connection points)
      - All topology edges (entity connectivity)
      - Diagnostic statistics
    """

    vertices: Dict[str, TopologyVertex] = Field(
        default_factory=dict,
        description="vertex_id → TopologyVertex"
    )
    edges: List[TopologyEdge] = Field(
        default_factory=list,
        description="All topology connections"
    )
    statistics: Dict[str, int] = Field(
        default_factory=dict,
        description="Graph diagnostic counters"
    )
