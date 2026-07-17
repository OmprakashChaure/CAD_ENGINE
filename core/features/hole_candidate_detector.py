"""
Hole Candidate Detector — deterministic concentric circular system detection.

Identifies structural hole candidates from concentric geometry groups.
Does NOT assign semantic manufacturing labels (drilled_hole, counterbore, etc.)

Produces:
  - Single-radius hole candidates (isolated circles)
  - Multi-radius hole candidates (concentric circle systems)

Preserves:
  - Radius ordering
  - Center precision
  - Entity traceability
  - Topology lineage
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


class HoleCandidateDetector:
    """
    Detect deterministic concentric circular system candidates.

    Input: entities + concentric_groups from StructuralPipeline
    Output: structural hole candidates (NOT semantic labels)
    """

    def detect(
        self,
        entities: List[Dict],
        concentric_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Detect hole-system candidates.

        Returns:
            {
                "hole_candidates": [
                    {
                        "candidate_id": "hc_00001",
                        "candidate_type": "single_radius" | "multi_radius",
                        "center": [x, y],
                        "radii": [r1, ...],
                        "entity_ids": [...],
                        "radius_count": int,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info("Detecting hole candidates")

        candidates: List[Dict] = []
        counter = 0

        # Multi-radius candidates from concentric groups
        concentric_groups = concentric_result.get("concentric_groups", [])

        for group in concentric_groups:
            counter += 1
            candidates.append({
                "candidate_id": f"hc_{counter:05d}",
                "candidate_type": "multi_radius",
                "center": group["center"],
                "radii": group["radii"],
                "entity_ids": group["entity_ids"],
                "radius_count": group["count"],
            })

        # Single-radius candidates from ungrouped circles
        ungrouped_ids = set(concentric_result.get("ungrouped_circles", []))
        entity_lookup = {e["entity_id"]: e for e in entities}

        for eid in sorted(ungrouped_ids):
            entity = entity_lookup.get(eid)
            if entity is None:
                continue
            etype = entity.get("entity_type")
            if etype not in ("CIRCLE", "ARC"):
                continue
            geometry = entity.get("geometry")
            if geometry is None:
                continue

            center = geometry.get("center")
            radius = geometry.get("radius")
            if center is None or radius is None:
                continue

            if etype == "ARC":
                start_angle = geometry.get("start_angle", 0.0)
                end_angle = geometry.get("end_angle", 0.0)
                sweep = (end_angle - start_angle) % 360
                if abs(sweep) < 1e-4:
                    sweep = 360.0
                if sweep <= 190.0:
                    continue

            counter += 1
            candidates.append({
                "candidate_id": f"hc_{counter:05d}",
                "candidate_type": "single_radius",
                "center": center,
                "radii": [round(radius, 4)],
                "entity_ids": [eid],
                "radius_count": 1,
            })

        single_count = sum(
            1 for c in candidates if c["candidate_type"] == "single_radius"
        )
        multi_count = len(candidates) - single_count

        logger.info(
            f"HoleCandidateDetector: candidates={len(candidates)} "
            f"(single={single_count} multi={multi_count})"
        )

        return {
            "hole_candidates": candidates,
            "statistics": {
                "total_candidates": len(candidates),
                "single_radius_candidates": single_count,
                "multi_radius_candidates": multi_count,
            },
        }
