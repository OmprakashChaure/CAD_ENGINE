"""
Contour Extractor — deterministic engineering contour chain detection.

Extracts contour chains by traversing topology connectivity.
Contours emerge ONLY from shared topology vertices — NOT from
visual proximity or semantic inference.

Produces:
  - Open contour chains (sequences of connected entities)
  - Closed contour loops (cycles returning to start vertex)
  - Isolated entities (no topology connections)

Preserves:
  - Traversal order
  - Entity lineage
  - Vertex lineage
"""
from typing import Any, Dict, List, Set, Tuple
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class ContourExtractor:
    """
    Extract deterministic contour chains from topology adjacency.

    Input: topology result (shared_vertices, edges, adjacency_list)
    Output: list of contour chains with entity ordering and metadata
    """

    def extract(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract contours from topology graph.

        Returns:
            {
                "contours": [
                    {
                        "contour_id": "ctr_00001",
                        "entity_ids": [...],
                        "vertex_ids": [...],
                        "is_closed": bool,
                        "length": int,
                    }
                ],
                "isolated_entities": [...],
                "statistics": { ... }
            }
        """
        logger.info("Extracting contours from topology")

        adjacency_list = topology_result.get("adjacency_list", {})
        shared_vertices = topology_result.get("shared_vertices", {})

        if not adjacency_list:
            # No topology connections — all entities are isolated
            isolated = [e["entity_id"] for e in entities]
            logger.info(
                f"ContourExtractor: no topology — "
                f"{len(isolated)} isolated entities"
            )
            return {
                "contours": [],
                "isolated_entities": isolated,
                "statistics": {
                    "total_contours": 0,
                    "closed_contours": 0,
                    "open_contours": 0,
                    "isolated_entities": len(isolated),
                },
            }

        # Build vertex→entity lookup for traversal ordering
        vertex_to_entities = self._build_vertex_entity_map(shared_vertices)

        # Traverse connected components as contour chains
        contours = self._traverse_contours(adjacency_list, vertex_to_entities)

        # Identify isolated entities (not in any contour)
        contour_entity_ids: Set[str] = set()
        for c in contours:
            contour_entity_ids.update(c["entity_ids"])

        all_entity_ids = {e["entity_id"] for e in entities}
        isolated = sorted(all_entity_ids - contour_entity_ids)

        closed_count = sum(1 for c in contours if c["is_closed"])
        open_count = len(contours) - closed_count

        logger.info(
            f"ContourExtractor: contours={len(contours)} "
            f"(closed={closed_count} open={open_count}) "
            f"isolated={len(isolated)}"
        )

        return {
            "contours": contours,
            "isolated_entities": isolated,
            "statistics": {
                "total_contours": len(contours),
                "closed_contours": closed_count,
                "open_contours": open_count,
                "isolated_entities": len(isolated),
            },
        }

    def _build_vertex_entity_map(
        self, shared_vertices: Dict
    ) -> Dict[str, List[str]]:
        """Map vertex_id → list of entity_ids at that vertex."""
        result = {}
        for vid, vdata in shared_vertices.items():
            result[vid] = vdata["connected_entities"]
        return result

    def _traverse_contours(
        self,
        adjacency_list: Dict[str, List[str]],
        vertex_to_entities: Dict[str, List[str]],
    ) -> List[Dict]:
        """
        Traverse connected components in the adjacency graph.
        Each connected component becomes one contour.
        """
        visited: Set[str] = set()
        contours: List[Dict] = []
        counter = 0

        # Get all entity_ids that participate in adjacency
        all_connected = set(adjacency_list.keys())

        for start_entity in sorted(all_connected):
            if start_entity in visited:
                continue

            # BFS traversal of this connected component
            chain = []
            queue = [start_entity]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                chain.append(current)

                neighbors = adjacency_list.get(current, [])
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append(neighbor)

            if not chain:
                continue

            counter += 1

            # Determine if closed: check if any entity connects
            # back to form a cycle (start entity has neighbor in chain end)
            is_closed = self._detect_closure(chain, adjacency_list)

            contours.append({
                "contour_id": f"ctr_{counter:05d}",
                "entity_ids": chain,
                "is_closed": is_closed,
                "length": len(chain),
            })

        return contours

    def _detect_closure(
        self,
        chain: List[str],
        adjacency_list: Dict[str, List[str]],
    ) -> bool:
        """
        Detect if a contour chain forms a closed loop.

        A chain is closed if every entity in it has degree >= 2
        within the chain (i.e., the subgraph has no leaf nodes).
        """
        if len(chain) < 3:
            return False

        chain_set = set(chain)
        for entity_id in chain:
            neighbors = adjacency_list.get(entity_id, [])
            # Count neighbors that are within this chain
            internal_degree = sum(
                1 for n in neighbors if n in chain_set
            )
            if internal_degree < 2:
                return False

        return True
