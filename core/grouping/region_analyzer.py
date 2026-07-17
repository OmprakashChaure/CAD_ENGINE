"""
Region Analyzer — analyze structural topology regions.

Detects disconnected structural regions (topology islands)
from the adjacency graph using connected component analysis.

Does NOT infer engineering meaning — only structural organization.

Produces:
  - Disconnected regions (isolated topology islands)
  - Region-to-entity mapping
  - Region size distribution

Preserves:
  - Entity traceability
  - Topology lineage
"""
from typing import Any, Dict, List, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class RegionAnalyzer:
    """
    Analyze structural topology regions via connected components.

    Each disconnected subgraph in the adjacency graph becomes
    a separate structural region.

    Isolated entities (no adjacency) form singleton regions.
    """

    def analyze(
        self,
        entities: List[Dict],
        adjacency_list: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """
        Partition entities into disconnected structural regions.

        Args:
            entities: list of canonical entities (post-filtering)
            adjacency_list: topology adjacency from TopologyPipeline

        Returns:
            {
                "regions": [
                    {
                        "region_id": "reg_00001",
                        "entity_ids": [...],
                        "size": int,
                        "is_singleton": bool,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"RegionAnalyzer: partitioning {len(entities)} entities"
        )

        all_entity_ids = [e["entity_id"] for e in entities]

        # Find connected components via BFS
        regions = self._find_connected_components(
            all_entity_ids, adjacency_list
        )

        # Classify regions
        singletons = sum(1 for r in regions if r["is_singleton"])
        multi_entity = len(regions) - singletons

        # Size distribution
        sizes = [r["size"] for r in regions]
        max_size = max(sizes) if sizes else 0
        min_size = min(sizes) if sizes else 0

        logger.info(
            f"RegionAnalyzer: regions={len(regions)} "
            f"(multi={multi_entity} singletons={singletons}) "
            f"size_range=[{min_size}, {max_size}]"
        )

        return {
            "regions": regions,
            "statistics": {
                "total_regions": len(regions),
                "multi_entity_regions": multi_entity,
                "singleton_regions": singletons,
                "max_region_size": max_size,
                "min_region_size": min_size,
                "total_entities": len(all_entity_ids),
            },
        }

    def _find_connected_components(
        self,
        all_entity_ids: List[str],
        adjacency_list: Dict[str, List[str]],
    ) -> List[Dict]:
        """
        Find all connected components using BFS traversal.

        Entities not in adjacency_list are treated as singletons.
        """
        visited: Set[str] = set()
        regions: List[Dict] = []
        counter = 0

        for entity_id in all_entity_ids:
            if entity_id in visited:
                continue

            # BFS from this entity
            component: List[str] = []
            queue = [entity_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)

                neighbors = adjacency_list.get(current, [])
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append(neighbor)

            counter += 1
            regions.append({
                "region_id": f"reg_{counter:05d}",
                "entity_ids": component,
                "size": len(component),
                "is_singleton": len(component) == 1,
            })

        return regions
