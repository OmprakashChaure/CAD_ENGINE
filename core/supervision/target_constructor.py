"""
Target Constructor — build explicit supervised prediction targets.

For each geometry entity, determines which dimensions are valid
inference targets based on:
  - Measurability (geometry-derived, deterministic)
  - Structural justification (topology, repetition, feature context)
  - Prediction eligibility (non-trivial, engineering-relevant)

Does NOT:
  - Invent semantic labels
  - Assume manufacturing intent
  - Hallucinate geometry meaning
  - Force engineering assumptions

Every target answers: "Could a real engineering drawing reasonably
require inference of this value?"
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)

# Minimum dimension value to be considered a valid target
# (filters out near-zero noise dimensions)
MIN_TARGET_VALUE = 0.1


class TargetConstructor:
    """
    Construct deterministic prediction targets from context packages.

    Target types:
      - length: line endpoint distance
      - diameter: circle diameter
      - radius: circle/arc radius
      - width: polyline bounding width
      - height: polyline bounding height

    Eligibility criteria:
      - Value > MIN_TARGET_VALUE (non-trivial)
      - Geometry is measurable (not degenerate)
      - Structural context exists (not completely isolated noise)
    """

    def __init__(self, min_value: float = MIN_TARGET_VALUE):
        self.min_value = min_value

    def construct(
        self,
        context_packages: List[Dict],
    ) -> Dict[str, Any]:
        """
        Build prediction targets from context packages.

        Returns:
            {
                "targets": [
                    {
                        "target_id": "tgt_00001",
                        "entity_id": str,
                        "entity_type": str,
                        "dimension_type": str,
                        "target_value": float,
                        "derivation": str,
                        "structural_justification": str,
                        "has_repetition_constraint": bool,
                        "has_concentric_constraint": bool,
                        "has_topology_context": bool,
                        "eligible": bool,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"TargetConstructor: constructing targets "
            f"from {len(context_packages)} packages"
        )

        targets: List[Dict] = []
        counter = 0

        for pkg in context_packages:
            entity_id = pkg["entity_id"]
            entity_type = pkg["entity_type"]
            own_dims = pkg.get("own_dimensions", [])

            for dim in own_dims:
                value = dim["value"]
                dim_type = dim["dimension_type"]

                # Eligibility check
                eligible, justification = self._evaluate_eligibility(
                    pkg, dim_type, value
                )

                if value < self.min_value:
                    eligible = False
                    justification = "below_minimum_threshold"

                counter += 1
                targets.append({
                    "target_id": f"tgt_{counter:05d}",
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "dimension_type": dim_type,
                    "target_value": value,
                    "derivation": self._get_derivation(entity_type, dim_type),
                    "structural_justification": justification,
                    "has_repetition_constraint": pkg.get("repetition_group") is not None,
                    "has_concentric_constraint": pkg.get("concentric_group") is not None,
                    "has_topology_context": len(pkg.get("topology_neighbors", [])) > 0,
                    "eligible": eligible,
                })

        eligible_count = sum(1 for t in targets if t["eligible"])
        ineligible_count = len(targets) - eligible_count

        logger.info(
            f"TargetConstructor: targets={len(targets)} "
            f"eligible={eligible_count} ineligible={ineligible_count}"
        )

        return {
            "targets": targets,
            "statistics": {
                "total_targets": len(targets),
                "eligible_targets": eligible_count,
                "ineligible_targets": ineligible_count,
                "by_type": self._count_by_type(targets),
                "by_entity_type": self._count_by_entity_type(targets),
            },
        }

    def _evaluate_eligibility(
        self,
        pkg: Dict,
        dim_type: str,
        value: float,
    ) -> tuple:
        """
        Determine if a dimension is a valid inference target.

        Returns: (eligible: bool, justification: str)
        """
        # Has topology context — connected to other geometry
        has_topo = len(pkg.get("topology_neighbors", [])) > 0

        # Has feature membership — structurally recognized
        has_feature = pkg.get("feature_membership") is not None

        # Has repetition constraint — same-dimension siblings exist
        has_repetition = pkg.get("repetition_group") is not None

        # Has concentric constraint — radius hierarchy exists
        has_concentric = pkg.get("concentric_group") is not None

        # Region context — not completely isolated noise
        region_size = pkg.get("region_size", 1)

        # Eligibility: at least ONE structural signal exists
        if has_topo:
            return True, "topology_connected"
        if has_feature:
            return True, "feature_candidate_member"
        if has_repetition:
            return True, "repetition_constrained"
        if has_concentric:
            return True, "concentric_hierarchy"
        if region_size > 1:
            return True, "multi_entity_region"

        # Isolated entity with no structural context
        # Still eligible if it's a measurable geometric primitive
        if dim_type in ("diameter", "radius"):
            return True, "measurable_circular_geometry"
        if dim_type == "length" and value > 1.0:
            return True, "measurable_linear_geometry"
        if dim_type in ("width", "height") and value > 1.0:
            return True, "measurable_contour_geometry"

        return False, "insufficient_structural_context"

    def _get_derivation(self, entity_type: str, dim_type: str) -> str:
        """Explain how the target value was derived."""
        derivations = {
            ("LINE", "length"): "line_endpoint_distance",
            ("CIRCLE", "radius"): "circle_radius_attribute",
            ("CIRCLE", "diameter"): "circle_diameter_computed",
            ("ARC", "radius"): "arc_radius_attribute",
            ("LWPOLYLINE", "width"): "polyline_bounding_width",
            ("LWPOLYLINE", "height"): "polyline_bounding_height",
            ("POLYLINE", "width"): "polyline_bounding_width",
            ("POLYLINE", "height"): "polyline_bounding_height",
        }
        return derivations.get((entity_type, dim_type), "geometry_derived")

    def _count_by_type(self, targets: List[Dict]) -> Dict[str, int]:
        """Count eligible targets by dimension type."""
        counts: Dict[str, int] = {}
        for t in targets:
            if t["eligible"]:
                dt = t["dimension_type"]
                counts[dt] = counts.get(dt, 0) + 1
        return counts

    def _count_by_entity_type(self, targets: List[Dict]) -> Dict[str, int]:
        """Count eligible targets by entity type."""
        counts: Dict[str, int] = {}
        for t in targets:
            if t["eligible"]:
                et = t["entity_type"]
                counts[et] = counts.get(et, 0) + 1
        return counts
