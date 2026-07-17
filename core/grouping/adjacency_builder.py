"""
Adjacency Builder — deterministic engineering connectivity.

Builds entity-to-entity topology edges derived ONLY from shared vertices.

Does NOT use:
  - Distance heuristics
  - Visual closeness
  - Layer assumptions
  - Brute-force comparisons

Adjacency is topology-derived ONLY.
"""
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum entities sharing a single vertex before it's considered a hub.
# Hubs with too many connections are likely noise (e.g., origin point).
# Loaded from configs/thresholds.yaml (relationships.max_hub_connections) at startup.
MAX_HUB_SIZE = 8


def _load_max_hub_size() -> int:
    """Load max_hub_connections from thresholds.yaml; fall back to MAX_HUB_SIZE."""
    try:
        import yaml
        config_path = Path(__file__).parents[2] / "configs" / "thresholds.yaml"
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            return int(cfg.get("relationships", {}).get("max_hub_connections", MAX_HUB_SIZE))
    except Exception:
        pass
    return MAX_HUB_SIZE


_CFG_MAX_HUB_SIZE = _load_max_hub_size()


class AdjacencyBuilder:
    """
    Builds topology adjacency from shared vertices.

    Produces deduplicated, directional-independent edges.
    Prevents hub explosion at high-connectivity vertices.
    """

    def __init__(self, max_hub_size: int = _CFG_MAX_HUB_SIZE):
        self.max_hub_size = max_hub_size

    def build(
        self,
        shared_vertices: Dict[str, Dict],
    ) -> Dict[str, any]:
        """
        Build adjacency graph from shared vertex data.

        Args:
            shared_vertices: { vertex_id: { vertex_id, x, y, connected_entities } }

        Returns:
            {
                "edges": [ { source, target, shared_vertex_id } ],
                "adjacency_list": { entity_id: [connected_entity_ids] },
                "statistics": { ... }
            }
        """
        logger.info("Building adjacency graph")

        edges: List[Dict] = []
        seen_pairs: Set[Tuple[str, str]] = set()
        adjacency_list: Dict[str, Set[str]] = defaultdict(set)
        skipped_hubs = 0

        for vertex_id, vertex_data in shared_vertices.items():
            entity_ids = vertex_data["connected_entities"]

            # Skip hub vertices (too many connections = likely noise)
            if len(entity_ids) > self.max_hub_size:
                skipped_hubs += 1
                logger.debug(
                    f"Skipping hub vertex {vertex_id} "
                    f"with {len(entity_ids)} connections"
                )
                continue

            # Generate pairwise edges (deduplicated)
            for i in range(len(entity_ids)):
                for j in range(i + 1, len(entity_ids)):
                    src = entity_ids[i]
                    tgt = entity_ids[j]

                    # Canonical pair ordering for deduplication
                    pair = (min(src, tgt), max(src, tgt))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    edges.append({
                        "source_entity_id": pair[0],
                        "target_entity_id": pair[1],
                        "shared_vertex_id": vertex_id,
                    })

                    adjacency_list[pair[0]].add(pair[1])
                    adjacency_list[pair[1]].add(pair[0])

        # Convert sets to sorted lists for deterministic output
        adjacency_sorted = {
            k: sorted(list(v))
            for k, v in adjacency_list.items()
        }

        logger.info(
            f"AdjacencyBuilder: edges={len(edges)} "
            f"connected_entities={len(adjacency_sorted)} "
            f"skipped_hubs={skipped_hubs}"
        )

        return {
            "edges": edges,
            "adjacency_list": adjacency_sorted,
            "statistics": {
                "total_edges": len(edges),
                "connected_entities": len(adjacency_sorted),
                "skipped_hub_vertices": skipped_hubs,
                "max_hub_size_threshold": self.max_hub_size,
            },
        }
