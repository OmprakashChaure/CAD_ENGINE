"""
Context Cluster Analyzer — group structurally related candidate systems.

Identifies connected components in the candidate relationship graph
to form structural context clusters.

Clusters are NOT engineering assemblies.
They are ONLY structural context groups.

Preserves:
  - Cluster lineage
  - Ambiguity metadata
  - Structural traceability
"""
from typing import Any, Dict, List, Set
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class ContextClusterAnalyzer:
    """
    Group structurally related candidates into context clusters.

    Uses connected components in the candidate relationship graph.
    Isolated candidates form singleton clusters.
    """

    def analyze(
        self,
        candidate_adjacency: Dict[str, List[str]],
        all_candidate_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Partition candidates into structural context clusters.

        Args:
            candidate_adjacency: { candidate_id: [related_ids] }
            all_candidate_ids: complete list of candidate IDs

        Returns:
            {
                "clusters": [
                    {
                        "cluster_id": "ctx_00001",
                        "candidate_ids": [...],
                        "size": int,
                        "is_singleton": bool,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"ContextClusterAnalyzer: clustering "
            f"{len(all_candidate_ids)} candidates"
        )

        visited: Set[str] = set()
        clusters: List[Dict] = []
        counter = 0

        for cid in sorted(all_candidate_ids):
            if cid in visited:
                continue

            # BFS traversal
            component: List[str] = []
            queue = [cid]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)

                neighbors = candidate_adjacency.get(current, [])
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append(neighbor)

            counter += 1
            clusters.append({
                "cluster_id": f"ctx_{counter:05d}",
                "candidate_ids": component,
                "size": len(component),
                "is_singleton": len(component) == 1,
            })

        singletons = sum(1 for c in clusters if c["is_singleton"])
        multi = len(clusters) - singletons
        max_size = max((c["size"] for c in clusters), default=0)

        logger.info(
            f"ContextClusterAnalyzer: clusters={len(clusters)} "
            f"(multi={multi} singletons={singletons}) "
            f"max_size={max_size}"
        )

        return {
            "clusters": clusters,
            "statistics": {
                "total_clusters": len(clusters),
                "multi_candidate_clusters": multi,
                "singleton_clusters": singletons,
                "max_cluster_size": max_size,
                "total_candidates": len(all_candidate_ids),
            },
        }
