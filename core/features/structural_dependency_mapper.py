"""
Structural Dependency Mapper — map deterministic structural dependencies.

Detects nested structural relationships where one candidate
structurally contains or depends on another (e.g., a radial pattern
depends on its member hole candidates).

Dependencies are NOT manufacturing dependencies.
Only structural graph relationships.

Preserves:
  - Deterministic hierarchy
  - Lineage integrity
  - Ambiguity visibility
"""
from typing import Any, Dict, List, Set
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class StructuralDependencyMapper:
    """
    Map deterministic structural dependencies between candidates.

    Dependency types:
      - contains: parent structurally contains child (pattern → members)
      - nested_in: child is nested within parent (concentric inner → outer)
    """

    def map(
        self,
        feature_result: Dict[str, Any],
        hierarchy_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build structural dependency map.

        Args:
            feature_result: from FeaturePipeline
            hierarchy_result: from FeatureHierarchyBuilder

        Returns:
            {
                "dependencies": [
                    {
                        "parent_id": str,
                        "child_id": str,
                        "dependency_type": str,
                    }
                ],
                "dependency_graph": { parent_id: [child_ids] },
                "root_candidates": [...],
                "leaf_candidates": [...],
                "statistics": { ... }
            }
        """
        logger.info("Mapping structural dependencies")

        dependencies: List[Dict] = []
        dep_graph: Dict[str, List[str]] = defaultdict(list)
        all_children: Set[str] = set()
        all_parents: Set[str] = set()

        # Extract from hierarchy nodes
        hierarchy_nodes = hierarchy_result.get("hierarchy_nodes", [])

        for node in hierarchy_nodes:
            parent_id = node.get("parent_id")
            candidate_id = node["candidate_id"]
            children = node.get("children_ids", [])

            if parent_id is not None:
                dependencies.append({
                    "parent_id": parent_id,
                    "child_id": candidate_id,
                    "dependency_type": "contains",
                })
                dep_graph[parent_id].append(candidate_id)
                all_children.add(candidate_id)
                all_parents.add(parent_id)

            for child_id in children:
                if child_id != candidate_id:
                    dep_key = (candidate_id, child_id)
                    # Avoid duplicates
                    existing = any(
                        d["parent_id"] == candidate_id and d["child_id"] == child_id
                        for d in dependencies
                    )
                    if not existing:
                        dependencies.append({
                            "parent_id": candidate_id,
                            "child_id": child_id,
                            "dependency_type": "contains",
                        })
                        dep_graph[candidate_id].append(child_id)
                        all_children.add(child_id)
                        all_parents.add(candidate_id)

        # Concentric nesting: inner radius nested in outer radius
        hole_candidates = feature_result.get(
            "hole_candidates", {}
        ).get("hole_candidates", [])

        for hc in hole_candidates:
            if hc["candidate_type"] == "multi_radius" and hc["radius_count"] >= 2:
                # The multi-radius candidate itself is the container
                # Individual entity_ids represent nested levels
                # (already captured in hierarchy — no additional deps needed)
                pass

        # Identify roots and leaves
        all_ids = all_parents | all_children
        roots = sorted(all_parents - all_children)
        leaves = sorted(all_children - all_parents)

        # Deduplicate dep_graph
        dep_graph_sorted = {
            k: sorted(list(set(v))) for k, v in dep_graph.items()
        }

        logger.info(
            f"DependencyMapper: dependencies={len(dependencies)} "
            f"roots={len(roots)} leaves={len(leaves)}"
        )

        return {
            "dependencies": dependencies,
            "dependency_graph": dep_graph_sorted,
            "root_candidates": roots,
            "leaf_candidates": leaves,
            "statistics": {
                "total_dependencies": len(dependencies),
                "root_count": len(roots),
                "leaf_count": len(leaves),
                "total_involved_candidates": len(all_ids),
            },
        }
