"""
Context Packager — deterministic engineering reasoning context for each entity.

For every geometry entity, packages the structural evidence that could
help infer its missing dimensions:
  - Topology neighbors (connected entities)
  - Feature candidate membership
  - Repetition group membership (same-dimension siblings)
  - Concentric group membership (radius hierarchy)
  - Region membership
  - Computable dimensions of neighbors

Does NOT:
  - Create embeddings or vectors
  - Infer manufacturing meaning
  - Hallucinate semantic context
  - Add probabilistic reasoning

Every field answers: "Would this help infer a missing dimension?"
"""
from typing import Any, Dict, List, Set
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class ContextPackager:
    """
    Package deterministic reasoning context per entity.

    For each geometry entity, collects:
      - Its own computable dimensions
      - Topology neighbors and their dimensions
      - Feature candidate it belongs to
      - Repetition group (entities with same dimensions)
      - Concentric group (radius hierarchy)
    """

    def package(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
        structural_result: Dict[str, Any],
        feature_result: Dict[str, Any],
        refinement_result: Dict[str, Any],
        computable_dimensions: List[Dict],
    ) -> List[Dict]:
        """
        Build context packages for all geometry entities.

        Returns list of context packages, one per geometry entity:
        [
            {
                "entity_id": str,
                "entity_type": str,
                "own_dimensions": [...],
                "topology_neighbors": [...],
                "neighbor_dimensions": [...],
                "feature_membership": {...} | None,
                "repetition_group": {...} | None,
                "concentric_group": {...} | None,
                "region_size": int,
            }
        ]
        """
        logger.info(
            f"ContextPackager: packaging {len(entities)} entities"
        )

        # Build lookups
        dims_by_entity = self._index_dimensions(computable_dimensions)
        adjacency = topology_result.get("adjacency_list", {})
        feature_membership = self._index_feature_membership(feature_result)
        repetition_membership = self._index_repetition_membership(refinement_result, feature_result)
        concentric_membership = self._index_concentric_membership(structural_result)
        region_sizes = self._index_region_sizes(structural_result)
        hierarchy_membership = self._index_hierarchy(structural_result)

        # Package each geometry entity
        packages: List[Dict] = []

        for entity in entities:
            etype = entity.get("entity_type", "")
            # Skip supervision entities — they are targets, not inputs
            if etype in ("DIMENSION", "TEXT", "MTEXT"):
                continue

            eid = entity.get("entity_id", "")

            # Own dimensions
            own_dims = dims_by_entity.get(eid, [])

            # Topology neighbors
            neighbors = adjacency.get(eid, [])

            # Neighbor dimensions (what dimensions do connected entities have?)
            neighbor_dims = []
            for nid in neighbors[:6]:  # Cap at 6 to prevent explosion
                for d in dims_by_entity.get(nid, []):
                    neighbor_dims.append({
                        "neighbor_id": nid,
                        "dimension_type": d["dimension_type"],
                        "value": d["value"],
                    })

            # Feature membership
            feat_mem = feature_membership.get(eid)

            # Repetition group
            rep_mem = repetition_membership.get(eid)

            # Concentric group
            conc_mem = concentric_membership.get(eid)

            # Region size
            reg_size = region_sizes.get(eid, 1)

            # Contour hierarchy
            hier_mem = hierarchy_membership.get(eid)

            packages.append({
                "entity_id": eid,
                "entity_type": etype,
                "own_dimensions": own_dims,
                "topology_neighbors": neighbors,
                "neighbor_dimensions": neighbor_dims,
                "feature_membership": feat_mem,
                "repetition_group": rep_mem,
                "concentric_group": conc_mem,
                "contour_hierarchy": hier_mem,
                "region_size": reg_size,
            })

        logger.info(
            f"ContextPackager: packaged {len(packages)} entities"
        )

        return packages

    def _index_dimensions(
        self, computable: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """Index computable dimensions by entity_id."""
        result: Dict[str, List[Dict]] = defaultdict(list)
        for d in computable:
            result[d["entity_id"]].append({
                "dimension_type": d["dimension_type"],
                "value": d["value"],
            })
        return dict(result)

    def _index_feature_membership(
        self, feature_result: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Map entity_id → feature candidate info."""
        result: Dict[str, Dict] = {}

        for hc in feature_result.get("hole_candidates", {}).get("hole_candidates", []):
            for eid in hc.get("entity_ids", []):
                result[eid] = {
                    "candidate_id": hc["candidate_id"],
                    "candidate_type": hc["candidate_type"],
                    "radius_count": hc["radius_count"],
                }

        for sc in feature_result.get("slot_candidates", {}).get("slot_candidates", []):
            eid = sc.get("entity_id")
            if eid:
                # Handle both single entity_id (string) and multi-entity (list)
                if isinstance(eid, list):
                    # For multi-entity slots, index all entities
                    for e in eid:
                        result[e] = {
                            "candidate_id": sc["candidate_id"],
                            "candidate_type": "slot",
                            "aspect_ratio": sc.get("aspect_ratio"),
                        }
                else:
                    result[eid] = {
                        "candidate_id": sc["candidate_id"],
                        "candidate_type": "slot",
                        "aspect_ratio": sc.get("aspect_ratio"),
                    }

        return result

    def _index_repetition_membership(
        self, refinement_result: Dict[str, Any], feature_result: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Map entity_id → repetition group info (same-dimension siblings)."""
        result: Dict[str, Dict] = {}

        # Build candidate_id → list(entity_id) mapping from feature results
        # Ensure every candidate_id maps to a list of entity ids so downstream
        # indexing always iterates over entity ids (avoids unhashable-list keys).
        candidate_to_entity: Dict[str, List[str]] = {}

        for hc in feature_result.get("hole_candidates", {}).get("hole_candidates", []):
            c_id = hc.get("candidate_id")
            eids = list(hc.get("entity_ids", [])) or []
            candidate_to_entity[c_id] = eids

        for sc in feature_result.get("slot_candidates", {}).get("slot_candidates", []):
            c_id = sc.get("candidate_id")
            eid = sc.get("entity_id")
            if eid is None:
                candidate_to_entity[c_id] = []
            elif isinstance(eid, list):
                candidate_to_entity[c_id] = list(eid)
            else:
                candidate_to_entity[c_id] = [eid]

        # Propagate repetition groups to entity level
        rep_groups = refinement_result.get("repetitions", {}).get("repetition_groups", [])

        for rg in rep_groups:
            group_info = {
                "group_id": rg["group_id"],
                "repetition_count": rg["repetition_count"],
                "signature": rg["signature"],
            }
            for cid in rg.get("candidate_ids", []):
                eids = candidate_to_entity.get(cid, [])
                for eid in eids:
                    # only index scalar entity ids (strings)
                    if eid:
                        result[eid] = group_info

        return result

    def _index_concentric_membership(
        self, structural_result: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Map entity_id → concentric group info (radius hierarchy)."""
        result: Dict[str, Dict] = {}

        groups = structural_result.get("concentric_groups", {}).get("concentric_groups", [])

        for grp in groups:
            group_info = {
                "group_id": grp["group_id"],
                "radii": grp["radii"],
                "count": grp["count"],
            }
            for eid in grp.get("entity_ids", []):
                result[eid] = group_info

        return result

    def _index_region_sizes(
        self, structural_result: Dict[str, Any]
    ) -> Dict[str, int]:
        """Map entity_id → region size (how many entities in same region)."""
        result: Dict[str, int] = {}

        regions = structural_result.get("regions", {}).get("regions", [])

        for region in regions:
            size = region["size"]
            for eid in region.get("entity_ids", []):
                result[eid] = size

        return result

    def _index_hierarchy(
        self, structural_result: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Map entity_id → contour hierarchy info (containment role)."""
        result: Dict[str, Dict] = {}

        hierarchy = structural_result.get("contour_hierarchy", {}).get("hierarchy", [])

        for node in hierarchy:
            eid = node.get("entity_id")
            if eid:
                result[eid] = {
                    "contour_role": node["contour_role"],
                    "nesting_depth": node["nesting_depth"],
                    "child_count": len(node.get("children_ids", [])),
                    "has_parent": node.get("parent_id") is not None,
                }

        return result
