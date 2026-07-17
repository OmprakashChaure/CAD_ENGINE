from typing import Tuple


def safe_point(point) -> Tuple[float, float]:
    """
    Convert DXF vector into normalized tuple.
    """

    return (float(point.x), float(point.y))


def normalize_layer(layer: str) -> str:
    """
    Normalize DXF layer names.
    """

    if not layer:
        return "UNKNOWN"

    return layer.strip().upper()


def normalize_entity_type(entity) -> str:
    """
    Return normalized DXF entity type.
    """

    return entity.dxftype().upper()