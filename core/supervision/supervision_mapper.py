"""
Supervision Mapper — deterministic geometry ↔ dimension mapping.

Establishes which dimension/supervision entities belong to which
geometry entities, using ONLY deterministic geometric reasoning:
  - Target point proximity to geometry endpoints/centers
  - Dimension value matching to computable geometric measurements
  - Structural context from topology adjacency

Does NOT use:
  - Semantic guessing
  - Manufacturing assumptions
  - Probabilistic inference
  - Nearest-text heuristics without geometric grounding

Produces:
  - Supervision mappings (dimension → geometry associations)
  - Computable dimension candidates (geometry-derived measurements)
  - Unmapped supervision entities (for future resolution)
"""
from typing import Any, Dict, List, Optional, Tuple
import math

from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum distance for target_point → geometry association
ASSOCIATION_TOLERANCE = 1.0


class SupervisionMapper:
    """
    Map supervision entities (DIMENSION, TEXT) to geometry entities.

    Strategy:
      1. Extract all supervision entities from kept entities
      2. Extract all geometry entities from kept entities
      3. Compute measurable dimensions from geometry
      4. Associate supervision to geometry via target_points
      5. Produce training-ready supervision mappings
    """

    def __init__(self, tolerance: float = ASSOCIATION_TOLERANCE):
        self.tolerance = tolerance

    def map(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build supervision mappings from entities.

        Args:
            entities: all kept entities (geometry + supervision)
            topology_result: from TopologyPipeline

        Returns:
            {
                "supervision_entities": [...],
                "geometry_entities": [...],
                "computable_dimensions": [...],
                "supervision_mappings": [...],
                "unmapped_supervision": [...],
                "statistics": { ... }
            }
        """
        logger.info(
            f"SupervisionMapper: processing {len(entities)} entities"
        )

        # Separate supervision from geometry
        supervision_ents = []
        geometry_ents = []

        for entity in entities:
            etype = entity.get("entity_type", "") # Get the data form the dictionary 
            if etype == "DIMENSION": 
                supervision_ents.append(entity)
            elif etype in ("TEXT", "MTEXT"):
                # Only supervision-bearing text (has numeric_value)
                geom = entity.get("geometry", {})
                if geom.get("numeric_value") is not None:
                    supervision_ents.append(entity)
            else:
                geometry_ents.append(entity)

        # Compute measurable dimensions from geometry
        computable = self._compute_dimensions(geometry_ents)

        # Build supervision mappings
        mappings, unmapped = self._build_mappings(
            supervision_ents, geometry_ents, computable
        )

        logger.info(
            f"SupervisionMapper: "
            f"supervision={len(supervision_ents)} "
            f"geometry={len(geometry_ents)} "
            f"computable={len(computable)} "
            f"mapped={len(mappings)} "
            f"unmapped={len(unmapped)}"
        )

        return {
            "supervision_entities": [
                self._summarize_supervision(s) for s in supervision_ents
            ],
            "geometry_entities_count": len(geometry_ents),
            "computable_dimensions": computable,
            "supervision_mappings": mappings,
            "unmapped_supervision": unmapped,
            "statistics": {
                "total_supervision_entities": len(supervision_ents),
                "total_geometry_entities": len(geometry_ents),
                "total_computable_dimensions": len(computable),
                "total_mapped": len(mappings),
                "total_unmapped": len(unmapped),
            },
        }

    def _compute_dimensions(
        self, geometry_ents: List[Dict]
    ) -> List[Dict]:
        """
        Compute all measurable dimensions from geometry entities.

        These are the VALUES a model should learn to predict.
        """
        computable = []

        for entity in geometry_ents:
            etype = entity.get("entity_type", "")
            geom = entity.get("geometry", {})
            eid = entity.get("entity_id", "")

            if etype == "LINE":
                length = geom.get("length")
                if length and length > 0:
                    computable.append({
                        "entity_id": eid,
                        "dimension_type": "length",
                        "value": round(length, 4),
                        "derivation": "line_endpoint_distance",
                    })

            elif etype == "CIRCLE":
                radius = geom.get("radius")
                if radius and radius > 0:
                    computable.append({
                        "entity_id": eid,
                        "dimension_type": "radius",
                        "value": round(radius, 4),
                        "derivation": "circle_radius",
                    })
                    computable.append({
                        "entity_id": eid,
                        "dimension_type": "diameter",
                        "value": round(radius * 2, 4),
                        "derivation": "circle_diameter",
                    })

            elif etype == "ARC":
                radius = geom.get("radius")
                if radius and radius > 0:
                    computable.append({
                        "entity_id": eid,
                        "dimension_type": "radius",
                        "value": round(radius, 4),
                        "derivation": "arc_radius",
                    })

            elif etype in ("LWPOLYLINE", "POLYLINE"):
                points = geom.get("points", [])
                if len(points) >= 2:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    width = round(max(xs) - min(xs), 4)
                    height = round(max(ys) - min(ys), 4)
                    if width > 0:
                        computable.append({
                            "entity_id": eid,
                            "dimension_type": "width",
                            "value": width,
                            "derivation": "polyline_bounding_width",
                        })
                    if height > 0:
                        computable.append({
                            "entity_id": eid,
                            "dimension_type": "height",
                            "value": height,
                            "derivation": "polyline_bounding_height",
                        })

        return computable

    def _build_mappings(
        self,
        supervision_ents: List[Dict],
        geometry_ents: List[Dict],
        computable: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Associate supervision entities to geometry via target_points.

        Returns: (mappings, unmapped)
        """
        mappings = []
        unmapped = []

        if not supervision_ents:
            return mappings, unmapped

        # Build geometry lookup by position
        geo_by_id = {e["entity_id"]: e for e in geometry_ents}

        for sup in supervision_ents:
            geom = sup.get("geometry", {})
            sup_id = sup.get("entity_id", "")
            sup_value = geom.get("numeric_value") or geom.get("value")
            target_points = geom.get("target_points", [])
            position = geom.get("position", [0, 0])

            # Strategy 1: Match via target_points proximity
            matched_entity = self._match_by_target_points(
                target_points, geometry_ents
            )

            # Strategy 2: Match via value comparison to computable
            if matched_entity is None and sup_value is not None:
                matched_entity = self._match_by_value(
                    sup_value, computable, geometry_ents
                )

            if matched_entity is not None:
                mappings.append({
                    "supervision_entity_id": sup_id,
                    "geometry_entity_id": matched_entity,
                    "supervision_value": sup_value,
                    "mapping_method": "geometric_association",
                })
            else:
                unmapped.append({
                    "supervision_entity_id": sup_id,
                    "supervision_value": sup_value,
                    "reason": "no_geometric_match",
                })

        return mappings, unmapped

    def _match_by_target_points(
        self,
        target_points: List[List[float]],
        geometry_ents: List[Dict],
    ) -> Optional[str]:
        """Match supervision to geometry via target point proximity."""
        if not target_points:
            return None

        best_entity = None
        best_dist = float("inf")

        for tp in target_points:
            for entity in geometry_ents:
                geom = entity.get("geometry", {})
                etype = entity.get("entity_type", "")

                # Get reference points for this entity
                ref_points = self._get_reference_points(etype, geom)

                for rp in ref_points:
                    dist = math.sqrt(
                        (tp[0] - rp[0]) ** 2 + (tp[1] - rp[1]) ** 2
                    )
                    if dist < best_dist and dist < self.tolerance:
                        best_dist = dist
                        best_entity = entity.get("entity_id")

        return best_entity

    def _match_by_value(
        self,
        sup_value: float,
        computable: List[Dict],
        geometry_ents: List[Dict],
    ) -> Optional[str]:
        """Match supervision to geometry via value comparison."""
        if sup_value is None or sup_value <= 0:
            return None

        # Find computable dimensions matching this value (within 1%)
        for comp in computable:
            comp_value = comp["value"]
            if comp_value > 0:
                ratio = abs(sup_value - comp_value) / comp_value
                if ratio < 0.01:  # 1% tolerance
                    return comp["entity_id"]

        return None

    def _get_reference_points(
        self, etype: str, geom: Dict
    ) -> List[List[float]]:
        """Get geometric reference points for proximity matching."""
        points = []

        if etype == "LINE":
            start = geom.get("start")
            end = geom.get("end")
            if start:
                points.append(start)
            if end:
                points.append(end)

        elif etype in ("CIRCLE", "ARC"):
            center = geom.get("center")
            if center:
                points.append(center)

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            for pt in geom.get("points", [])[:4]:  # First 4 points only
                points.append(pt)

        return points

    def _summarize_supervision(self, entity: Dict) -> Dict:
        """Create a compact summary of a supervision entity."""
        geom = entity.get("geometry", {})
        return {
            "entity_id": entity.get("entity_id"),
            "entity_type": entity.get("entity_type"),
            "value": geom.get("numeric_value") or geom.get("value"),
            "dimension_type": geom.get("dimension_type", geom.get("text_role")),
            "text": geom.get("text", ""),
        }
