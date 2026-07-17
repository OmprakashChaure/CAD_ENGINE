"""
Concentric Grouping — detect deterministic concentric geometry systems.

Groups circles and arcs that share the same center point.
Concentricity is geometry-derived ONLY — no heuristic semantic grouping.

Produces:
  - Concentric groups (entities sharing center within tolerance)
  - Radius hierarchy within each group

Preserves:
  - Entity traceability
  - Geometry lineage
  - Radius ordering
"""
from typing import Any, Dict, List, Tuple
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)

# Center-matching tolerance (same as vertex indexer precision)
CENTER_PRECISION = 4


class ConcentricGrouping:
    """
    Detect concentric geometry systems from canonical entities.

    Groups CIRCLE and ARC entities whose centers match
    within configurable tolerance.

    Does NOT use:
      - Semantic inference
      - Layer assumptions
      - Visual proximity heuristics
    """

    def __init__(self, precision: int = CENTER_PRECISION):
        self.precision = precision

    def detect(
        self,
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """
        Detect concentric groups from filtered entities.

        Args:
            entities: list of canonical entities (post-filtering)

        Returns:
            {
                "concentric_groups": [
                    {
                        "group_id": "conc_00001",
                        "center": [x, y],
                        "entity_ids": [...],
                        "radii": [r1, r2, ...],  # sorted ascending
                        "count": int,
                    }
                ],
                "ungrouped_circles": [...],
                "statistics": { ... }
            }
        """
        logger.info("Detecting concentric groups")

        # Extract circles and arcs with centers
        center_entities = self._extract_center_entities(entities)

        if not center_entities:
            logger.info("ConcentricGrouping: no circle/arc entities")
            return {
                "concentric_groups": [],
                "ungrouped_circles": [],
                "statistics": {
                    "total_groups": 0,
                    "total_circle_arc_entities": 0,
                    "grouped_entities": 0,
                    "ungrouped_entities": 0,
                },
            }

        # Group by snapped center coordinate
        center_map: Dict[Tuple[float, float], List[Dict]] = defaultdict(list)

        for entry in center_entities:
            center_key = (
                round(entry["center"][0], self.precision),
                round(entry["center"][1], self.precision),
            )
            center_map[center_key].append(entry)

        # Build concentric groups (only centers with 2+ entities)
        groups: List[Dict] = []
        grouped_ids: set = set()
        counter = 0

        for center_key, entries in center_map.items():
            if len(entries) >= 2:
                counter += 1

                # Sort by radius ascending
                entries_sorted = sorted(
                    entries, key=lambda e: e["radius"]
                )

                entity_ids = [e["entity_id"] for e in entries_sorted]
                radii = [round(e["radius"], 4) for e in entries_sorted]

                groups.append({
                    "group_id": f"conc_{counter:05d}",
                    "center": [center_key[0], center_key[1]],
                    "entity_ids": entity_ids,
                    "radii": radii,
                    "count": len(entries_sorted),
                })

                grouped_ids.update(entity_ids)

        # Identify ungrouped circle/arc entities
        all_circle_ids = {e["entity_id"] for e in center_entities}
        ungrouped = sorted(all_circle_ids - grouped_ids)

        logger.info(
            f"ConcentricGrouping: groups={len(groups)} "
            f"grouped={len(grouped_ids)} "
            f"ungrouped={len(ungrouped)}"
        )

        return {
            "concentric_groups": groups,
            "ungrouped_circles": ungrouped,
            "statistics": {
                "total_groups": len(groups),
                "total_circle_arc_entities": len(center_entities),
                "grouped_entities": len(grouped_ids),
                "ungrouped_entities": len(ungrouped),
            },
        }

    def _extract_center_entities(
        self, entities: List[Dict]
    ) -> List[Dict]:
        """
        Extract entities that have a center + radius
        (CIRCLE and ARC types).
        """
        result = []

        for entity in entities:
            entity_type = entity.get("entity_type")
            geometry = entity.get("geometry")

            if geometry is None:
                continue

            if entity_type == "CIRCLE":
                center = geometry.get("center")
                radius = geometry.get("radius")
                if center and radius is not None and radius > 0:
                    result.append({
                        "entity_id": entity["entity_id"],
                        "entity_type": entity_type,
                        "center": center,
                        "radius": radius,
                    })

            elif entity_type == "ARC":
                center = geometry.get("center")
                radius = geometry.get("radius")
                if center and radius is not None and radius > 0:
                    result.append({
                        "entity_id": entity["entity_id"],
                        "entity_type": entity_type,
                        "center": center,
                        "radius": radius,
                    })

        return result
