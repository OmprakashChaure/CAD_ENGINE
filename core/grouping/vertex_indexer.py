"""
Vertex Indexer — creates stable shared geometric vertices.

Foundation of all topology graph construction.

Behavior:
  - Extracts endpoints from LINE, ARC, POLYLINE, LWPOLYLINE
  - Pass 1: merges near-identical coordinates using exact-match decimal rounding
  - Pass 2: optional near-match pass — merges remaining orphan endpoints within
    endpoint_snap_tolerance ONLY when exactly one candidate exists in range
    (avoids ambiguous merges when multiple candidates are within range)
  - Generates stable deterministic vertex IDs
  - Maintains entity ↔ vertex traceability
  - Logs every near-match merge with the gap distance for auditability

Does NOT:
  - Use distance heuristics for non-endpoint connections
  - Generate semantic relationships
  - Merge ambiguously (two or more candidates in range → no merge)
"""
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# Pass 1 — exact-match snapping: number of decimal places (0.0001 mm at 4)
VERTEX_PRECISION = 4

# Pass 2 — near-match tolerance in mm (default 0.001 mm = 10× looser than Pass 1)
# Only used when exactly ONE orphan endpoint is within this range of another.
ENDPOINT_SNAP_TOLERANCE = 0.001

# Config key paths (loaded once at module level from thresholds.yaml if available)
def _load_config_values() -> Tuple[int, float]:
    """Load vertex precision and near-match tolerance from thresholds.yaml."""
    try:
        import yaml
        config_path = Path(__file__).parents[2] / "configs" / "thresholds.yaml"
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            geo = cfg.get("geometry", {})
            precision = int(geo.get("vertex_exact_match_decimals", VERTEX_PRECISION))
            tolerance = float(geo.get("vertex_near_match_tolerance", ENDPOINT_SNAP_TOLERANCE))
            return precision, tolerance
    except Exception:
        pass
    return VERTEX_PRECISION, ENDPOINT_SNAP_TOLERANCE


_CFG_PRECISION, _CFG_TOLERANCE = _load_config_values()


class VertexIndexer:
    """
    Spatial vertex indexing engine.

    Converts geometric endpoints into hashable topology vertices.
    Only endpoints participate in topology — NOT centers.

    Two-pass snapping:
      Pass 1 — deterministic rounding to `precision` decimal places
      Pass 2 — near-match merge for remaining orphan endpoints within
               `endpoint_snap_tolerance` mm (unambiguous candidates only)
    """

    def __init__(
        self,
        precision: int = _CFG_PRECISION,
        endpoint_snap_tolerance: float = _CFG_TOLERANCE,
    ):
        self.precision = precision
        self.endpoint_snap_tolerance = endpoint_snap_tolerance
        # vertex_key → list of entity_ids that share this vertex
        self.vertex_map: Dict[Tuple[float, float], List[str]] = defaultdict(list)
        # vertex_key → stable vertex_id
        self.vertex_ids: Dict[Tuple[float, float], str] = {}
        self._counter = 0

    def _snap_vertex(self, x: float, y: float) -> Tuple[float, float]:
        """Round coordinates to precision for deterministic snapping (Pass 1)."""
        return (
            round(x, self.precision),
            round(y, self.precision),
        )

    def _get_vertex_id(self, key: Tuple[float, float]) -> str:
        """Get or create a stable vertex ID for a coordinate."""
        if key not in self.vertex_ids:
            self._counter += 1
            self.vertex_ids[key] = f"vtx_{self._counter:05d}"
        return self.vertex_ids[key]

    def _extract_endpoints(self, entity: Dict) -> List[Tuple[float, float]]:
        """
        Extract topology-relevant endpoints from entity geometry.

        Only ENDPOINTS participate in topology:
          - LINE: start, end
          - ARC: start_point, end_point (computed from center/angles)
          - POLYLINE/LWPOLYLINE: all sequential points (each is a potential connection)

        Centers do NOT participate — they are not connection points.
        """
        entity_type = entity["entity_type"]
        geometry = entity.get("geometry")

        if geometry is None:
            return []

        endpoints = []

        if entity_type == "LINE":
            start = geometry.get("start")
            end = geometry.get("end")
            if start and end:
                endpoints.append(self._snap_vertex(start[0], start[1]))
                endpoints.append(self._snap_vertex(end[0], end[1]))

        elif entity_type in ("LWPOLYLINE", "POLYLINE"):
            points = geometry.get("points", [])
            for pt in points:
                endpoints.append(self._snap_vertex(pt[0], pt[1]))

        elif entity_type == "ARC":
            # ARC endpoints computed from center + radius + angles
            center = geometry.get("center")
            radius = geometry.get("radius", 0)
            sa = geometry.get("start_angle", 0)
            ea = geometry.get("end_angle", 0)
            if center and radius > 0:
                # Start point
                sx = center[0] + radius * math.cos(math.radians(sa))
                sy = center[1] + radius * math.sin(math.radians(sa))
                endpoints.append(self._snap_vertex(sx, sy))
                # End point
                ex = center[0] + radius * math.cos(math.radians(ea))
                ey = center[1] + radius * math.sin(math.radians(ea))
                endpoints.append(self._snap_vertex(ex, ey))

        # CIRCLE: no endpoints (closed curve, no connection points)
        # PLANNED, NOT YET ACTIVE: CircleTangencyDetector post-processing step will
        # detect circle-to-line tangency and circle-to-polyline containment as a
        # separate relationship type (not merged into adjacency_list).

        return endpoints

    def _near_match_pass(
        self,
        orphan_keys: List[Tuple[float, float]],
    ) -> int:
        """
        Pass 2 — Near-match endpoint gap bridging.

        For each orphan endpoint, find all other orphan endpoints within
        `endpoint_snap_tolerance` mm. Only merge if EXACTLY ONE candidate exists
        in range. If two or more candidates are within range, skip (ambiguous).

        Every merge is logged with the exact gap distance for auditability.

        Args:
            orphan_keys: list of vertex_keys that have only one entity (not yet shared)

        Returns:
            Number of new merges performed.
        """
        if not orphan_keys or self.endpoint_snap_tolerance <= 0:
            return 0

        merges = 0
        # Use a union-find-like approach: track which orphans have been merged
        merged: Dict[Tuple[float, float], Tuple[float, float]] = {}

        for i in range(len(orphan_keys)):
            key_a = orphan_keys[i]
            if key_a in merged:
                continue  # Already consumed by a prior merge

            candidates = []
            for j in range(len(orphan_keys)):
                if i == j:
                    continue
                key_b = orphan_keys[j]
                if key_b in merged:
                    continue
                gap = math.hypot(key_a[0] - key_b[0], key_a[1] - key_b[1])
                if gap <= self.endpoint_snap_tolerance:
                    candidates.append((gap, key_b))

            if len(candidates) != 1:
                # 0 candidates: no close neighbour
                # 2+ candidates: ambiguous — do not merge, log as debug
                if len(candidates) > 1:
                    logger.debug(
                        f"Near-match SKIP: orphan {key_a} has {len(candidates)} "
                        f"candidates within {self.endpoint_snap_tolerance} mm — ambiguous"
                    )
                continue

            gap, key_b = candidates[0]

            # Merge key_b into key_a: reassign all entities from key_b to key_a
            entities_b = list(self.vertex_map[key_b])
            for eid in entities_b:
                if eid not in self.vertex_map[key_a]:
                    self.vertex_map[key_a].append(eid)
            del self.vertex_map[key_b]
            merged[key_b] = key_a

            logger.info(
                f"Near-match MERGE: {key_b} -> {key_a} "
                f"(gap={gap:.6f} mm, entities={entities_b})"
            )
            merges += 1

        return merges

    def build(self, entities: List[Dict]) -> Dict[str, Any]:
        """
        Build the vertex index from filtered entities.

        Pass 1: extract and exact-match snap all endpoints.
        Pass 2: near-match pass for remaining orphan endpoints.

        Returns:
            {
                "vertex_map": { vertex_key: [entity_ids] },
                "vertex_ids": { vertex_key: vertex_id },
                "shared_vertices": { vertex_id: { x, y, connected_entities } },
                "statistics": { ... }
            }
        """
        logger.info("Building vertex index")

        self.vertex_map.clear()
        self.vertex_ids.clear()
        self._counter = 0

        # ── PASS 1: exact-match snapping ─────────────────────────────────────
        for entity in entities:
            entity_id = entity["entity_id"]
            endpoints = self._extract_endpoints(entity)

            for vertex_key in endpoints:
                if entity_id not in self.vertex_map[vertex_key]:
                    self.vertex_map[vertex_key].append(entity_id)

        # ── PASS 2: near-match gap bridging ──────────────────────────────────
        # Identify orphan endpoints: vertices touched by exactly one entity
        orphan_keys = [
            key for key, eids in self.vertex_map.items() if len(eids) == 1
        ]
        near_match_merges = self._near_match_pass(orphan_keys)

        if near_match_merges > 0:
            logger.info(
                f"VertexIndexer: near-match pass merged {near_match_merges} orphan endpoint pairs"
            )
        else:
            logger.debug("VertexIndexer: near-match pass produced 0 new merges (expected on exact-match geometry)")

        # ── Build shared vertices (only vertices with 2+ entities) ────────────
        shared_vertices = {}
        for vertex_key, entity_ids in self.vertex_map.items():
            if len(entity_ids) >= 2:
                vid = self._get_vertex_id(vertex_key)
                shared_vertices[vid] = {
                    "vertex_id": vid,
                    "x": vertex_key[0],
                    "y": vertex_key[1],
                    "connected_entities": entity_ids,
                }

        total_vertices = len(self.vertex_map)
        shared_count = len(shared_vertices)
        orphan_count = total_vertices - shared_count

        logger.info(
            f"VertexIndexer: total={total_vertices} "
            f"shared={shared_count} orphan={orphan_count} "
            f"near_match_merges={near_match_merges}"
        )

        return {
            "vertex_map": dict(self.vertex_map),
            "vertex_ids": dict(self.vertex_ids),
            "shared_vertices": shared_vertices,
            "statistics": {
                "total_vertices": total_vertices,
                "shared_vertices": shared_count,
                "orphan_vertices": orphan_count,
                "entities_processed": len(entities),
                "near_match_merges": near_match_merges,
            },
        }
