"""
Loop Detector — detect closed engineering topology loops.

Identifies true topological cycles from contour data.
Does NOT hallucinate closure — only classifies verified cycles
where every entity connects back through shared vertices.

Produces:
  - Closed loops (verified topological cycles)
  - Open chains (non-cyclic connected components)

Preserves:
  - Topology lineage
  - Entity ordering
  - Vertex traceability
"""
from typing import Any, Dict, List, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class LoopDetector:
    """
    Detect closed topology loops from contour extraction results.

    A loop is a connected component where every entity has
    internal degree >= 2 (no leaf nodes in the subgraph).

    Does NOT force closure on open chains.
    Does NOT hallucinate loops from visual proximity.
    """

    def detect(
        self,
        contours: List[Dict],
        adjacency_list: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """
        Classify contours into verified loops and open chains.

        Args:
            contours: list from ContourExtractor
            adjacency_list: topology adjacency from TopologyPipeline

        Returns:
            {
                "loops": [
                    {
                        "loop_id": "loop_00001",
                        "contour_id": "ctr_00001",
                        "entity_ids": [...],
                        "length": int,
                        "min_degree": int,
                    }
                ],
                "open_chains": [
                    {
                        "chain_id": "chain_00001",
                        "contour_id": "ctr_00002",
                        "entity_ids": [...],
                        "length": int,
                        "leaf_entities": [...],
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"LoopDetector: analyzing {len(contours)} contours"
        )

        loops: List[Dict] = []
        open_chains: List[Dict] = []
        loop_counter = 0
        chain_counter = 0

        for contour in contours:
            entity_ids = contour["entity_ids"]
            contour_id = contour["contour_id"]

            if len(entity_ids) < 3:
                # Cannot form a loop with fewer than 3 entities
                chain_counter += 1
                open_chains.append({
                    "chain_id": f"chain_{chain_counter:05d}",
                    "contour_id": contour_id,
                    "entity_ids": entity_ids,
                    "length": len(entity_ids),
                    "leaf_entities": self._find_leaves(
                        entity_ids, adjacency_list
                    ),
                })
                continue

            # Verify true topological closure
            is_loop, min_degree = self._verify_loop(
                entity_ids, adjacency_list
            )

            if is_loop:
                loop_counter += 1
                loops.append({
                    "loop_id": f"loop_{loop_counter:05d}",
                    "contour_id": contour_id,
                    "entity_ids": entity_ids,
                    "length": len(entity_ids),
                    "min_degree": min_degree,
                })
            else:
                chain_counter += 1
                open_chains.append({
                    "chain_id": f"chain_{chain_counter:05d}",
                    "contour_id": contour_id,
                    "entity_ids": entity_ids,
                    "length": len(entity_ids),
                    "leaf_entities": self._find_leaves(
                        entity_ids, adjacency_list
                    ),
                })

        logger.info(
            f"LoopDetector: loops={len(loops)} "
            f"open_chains={len(open_chains)}"
        )

        return {
            "loops": loops,
            "open_chains": open_chains,
            "statistics": {
                "total_loops": len(loops),
                "total_open_chains": len(open_chains),
                "total_contours_analyzed": len(contours),
            },
        }

    def _verify_loop(
        self,
        entity_ids: List[str],
        adjacency_list: Dict[str, List[str]],
    ) -> tuple:
        """
        Verify that a contour forms a true topological loop.

        A loop requires every entity to have internal degree >= 2
        (no leaf nodes — every entity connects to at least 2 others
        within the same contour).

        Returns: (is_loop: bool, min_internal_degree: int)
        """
        chain_set = set(entity_ids)
        min_degree = float("inf")

        for entity_id in entity_ids:
            neighbors = adjacency_list.get(entity_id, [])
            internal_degree = sum(
                1 for n in neighbors if n in chain_set
            )
            min_degree = min(min_degree, internal_degree)

            if internal_degree < 2:
                return False, int(min_degree)

        return True, int(min_degree)

    def _find_leaves(
        self,
        entity_ids: List[str],
        adjacency_list: Dict[str, List[str]],
    ) -> List[str]:
        """
        Find leaf entities (degree 1) in an open chain.
        These are the endpoints of the chain.
        """
        chain_set = set(entity_ids)
        leaves = []

        for entity_id in entity_ids:
            neighbors = adjacency_list.get(entity_id, [])
            internal_degree = sum(
                1 for n in neighbors if n in chain_set
            )
            if internal_degree <= 1:
                leaves.append(entity_id)

        return leaves
