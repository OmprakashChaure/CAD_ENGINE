"""
Feature Hierarchy Builder — deterministic structural candidate hierarchies.

Organizes feature candidates into parent-child structural relationships
based on geometric containment and concentric nesting.

Hierarchy does NOT imply engineering meaning — only structural organization.

Produces:
  - Parent-child candidate relationships
  - Nesting depth information

Preserves:
  - Candidate lineage
  - Topology ownership
  - Contour relationships
"""
from typing import Any, Dict, List, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class FeatureHierarchyBuilder:
    """
    Build deterministic structural candidate hierarchies.

    Detects containment relationships between candidates:
      - Multi-radius hole candidates contain their inner radii
      - Radial patterns contain their member hole candidates
      - Feature regions contain their associated candidates

    Does NOT imply engineering meaning or manufacturing hierarchy.
    """

    def build(
        self,
        feature_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build structural hierarchy from feature candidates.

        Returns:
            {
                "hierarchy_nodes": [
                    {
                        "candidate_id": str,
                        "parent_id": str | None,
                        "children_ids": [...],
                        "depth": int,
                        "hierarchy_type": str,
                    }
                ],
                "root_candidates": [...],
                "statistics": { ... }
            }
        """
        logger.info("Building feature hierarchy")

        nodes: List[Dict] = []
        root_ids: List[str] = []

        hole_candidates = feature_result.get(
            "hole_candidates", {}
        ).get("hole_candidates", [])

        radial_patterns = feature_result.get(
            "radial_patterns", {}
        ).get("radial_patterns", [])

        # Track which candidates are children
        child_ids: Set[str] = set()

        # Radial patterns are parents of their member hole candidates
        for rp in radial_patterns:
            pattern_id = rp["pattern_id"]
            member_ids = rp.get("member_candidate_ids", [])

            nodes.append({
                "candidate_id": pattern_id,
                "parent_id": None,
                "children_ids": member_ids,
                "depth": 0,
                "hierarchy_type": "radial_pattern_parent",
            })
            root_ids.append(pattern_id)

            for mid in member_ids:
                child_ids.add(mid)
                nodes.append({
                    "candidate_id": mid,
                    "parent_id": pattern_id,
                    "children_ids": [],
                    "depth": 1,
                    "hierarchy_type": "pattern_member",
                })

        # Multi-radius hole candidates are self-contained hierarchies
        for hc in hole_candidates:
            cid = hc["candidate_id"]
            if cid in child_ids:
                continue  # Already placed as child of a pattern

            if hc["candidate_type"] == "multi_radius":
                nodes.append({
                    "candidate_id": cid,
                    "parent_id": None,
                    "children_ids": [],
                    "depth": 0,
                    "hierarchy_type": "multi_radius_system",
                })
                root_ids.append(cid)
            else:
                # Single-radius not in any pattern — standalone root
                nodes.append({
                    "candidate_id": cid,
                    "parent_id": None,
                    "children_ids": [],
                    "depth": 0,
                    "hierarchy_type": "standalone",
                })
                root_ids.append(cid)

        max_depth = max((n["depth"] for n in nodes), default=0)

        logger.info(
            f"HierarchyBuilder: nodes={len(nodes)} "
            f"roots={len(root_ids)} max_depth={max_depth}"
        )

        return {
            "hierarchy_nodes": nodes,
            "root_candidates": root_ids,
            "statistics": {
                "total_nodes": len(nodes),
                "root_count": len(root_ids),
                "max_depth": max_depth,
                "pattern_children": len(child_ids),
            },
        }
