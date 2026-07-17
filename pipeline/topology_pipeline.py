"""
Topology Pipeline — geometry → deterministic engineering topology.

Stages:
  1. Vertex indexing (shared endpoint detection)
  2. Adjacency construction (entity connectivity)
  3. Topology validation (consistency checks)

Does NOT:
  - Perform semantic inference
  - Generate feature reasoning
  - Create manufacturing logic
  - Build AI-generated relationships
"""
from typing import Any, Dict, List

from core.grouping.vertex_indexer import VertexIndexer
from core.grouping.adjacency_builder import AdjacencyBuilder
from utils.logger import get_logger

logger = get_logger(__name__)


class TopologyPipeline:
    """
    Orchestrate topology graph construction from filtered entities.

    Input: list of canonical entities (post-filtering)
    Output: topology graph structure with vertices, edges, statistics
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(self, entities: List[Dict]) -> Dict[str, Any]:
        """
        Build topology graph from filtered entities.

        Returns:
            {
                "shared_vertices": { ... },
                "edges": [ ... ],
                "adjacency_list": { ... },
                "statistics": { ... }
            }
        """
        logger.info(
            f"TopologyPipeline: processing {len(entities)} entities"
        )

        # Stage 1: Vertex indexing
        indexer = VertexIndexer(
            precision=self.config.get("vertex_precision", 4)
        )
        vertex_result = indexer.build(entities)

        shared_vertices = vertex_result["shared_vertices"]

        # Stage 2: Adjacency construction
        builder = AdjacencyBuilder(
            max_hub_size=self.config.get("max_hub_size", 8)
        )
        adjacency_result = builder.build(shared_vertices)

        # Stage 3: Validation
        orphan_entities = self._detect_orphans(
            entities, adjacency_result["adjacency_list"]
        )

        # Combine statistics
        statistics = {
            **vertex_result["statistics"],
            **adjacency_result["statistics"],
            "orphan_entities": len(orphan_entities),
            "total_input_entities": len(entities),
        }

        logger.info(
            f"TopologyPipeline complete: "
            f"vertices={statistics['shared_vertices']} "
            f"edges={statistics['total_edges']} "
            f"orphans={statistics['orphan_entities']}"
        )

        return {
            "shared_vertices": shared_vertices,
            "edges": adjacency_result["edges"],
            "adjacency_list": adjacency_result["adjacency_list"],
            "orphan_entities": orphan_entities,
            "statistics": statistics,
        }

    def _detect_orphans(
        self,
        entities: List[Dict],
        adjacency_list: Dict[str, List[str]],
    ) -> List[str]:
        """
        Detect entities with no topology connections.
        These are isolated geometry (circles, short segments, etc.)
        """
        all_ids = {e["entity_id"] for e in entities}
        connected_ids = set(adjacency_list.keys())
        orphans = sorted(all_ids - connected_ids)
        return orphans
