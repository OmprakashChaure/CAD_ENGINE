from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel


# =========================================================
# BASE DXF ENTITY SCHEMAS
# =========================================================

class BaseEntity(BaseModel):
    """
    Base normalized DXF entity.
    """

    source_file: str
    entity_type: str
    handle: str
    layer: str
    linetype: Optional[str] = None
    color: Optional[int] = None


class LineEntity(BaseEntity):
    start: Tuple[float, float]
    end: Tuple[float, float]


class CircleEntity(BaseEntity):
    center: Tuple[float, float]
    radius: float


class ArcEntity(BaseEntity):
    center: Tuple[float, float]
    radius: float
    start_angle: float
    end_angle: float


class PolylineEntity(BaseEntity):
    points: List[Tuple[float, float]]
    closed: bool = False


class RawDXFEntity(BaseModel):
    """
    Generic normalized DXF entity wrapper.
    """

    metadata: BaseEntity
    geometry: Dict[str, Any]


# =========================================================
# FILTER PIPELINE SCHEMAS
# =========================================================

class FilteredEntity(BaseModel):
    entity: Dict[str, Any]
    reason: str
    confidence: float = 0.5

class EntityConfidence(BaseModel):

    possible_overlap: bool = False

    overlap_confidence: float = 0.0

class FilterStatistics(BaseModel):
    input_entities: int
    kept_entities: int
    quarantined_entities: int
    removed_entities: int


class FilterResult(BaseModel):
    kept_entities: List[Dict[str, Any]]
    quarantined_entities: List[FilteredEntity]
    removed_entities: List[FilteredEntity]
    statistics: FilterStatistics