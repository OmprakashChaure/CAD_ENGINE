"""
Feature Region Grouper — group structurally related feature candidates.

Associates feature candidates with their containing topology regions.
Does NOT force grouping — only links candidates that share
deterministic structural relationships.

Produces:
  - Feature-region associations
  - Candidate clusters within regions

Preserves:
  - Candidate lineage
  - Region traceability
  - Topology ownership
"""
from typing import Any, Dict, List, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class FeatureRegionGrouper:
    """
    Group feature candidates by their structural region membership.

    Associates hole/slot/pattern candidates with the topology
    regions they belong to, enabling future feature reasoning
    within bounded structural contexts.

    Does NOT force grouping across regions.
    """

    def group(
        self,
        hole_candidates: List[Dict],
        slot_candidates: List[Dict],
        radial_patterns: List[Dict],
        regions: List[Dict],
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """
        Associate feature candidates with topology regions.

        Returns:
            {
                "feature_regions": [
                    {
                        "region_id": str,
                        "hole_candidate_ids": [...],
                        "slot_candidate_ids": [...],
                        "radial_pattern_ids": [...],
                        "total_candidates": int,
                    }
                ],
                "unassigned_candidates": {
                    "holes": [...],
                    "slots": [...],
                    "patterns": [...],
                },
                "statistics": { ... }
            }
        """
        logger.info("Grouping feature candidates by region")

        # Build entity_id → region_id lookup
        entity_to_region: Dict[str, str] = {}
        for region in regions:
            for eid in region["entity_ids"]:
                entity_to_region[eid] = region["region_id"]

        # Assign hole candidates to regions
        hole_region_map: Dict[str, List[str]] = {}
        unassigned_holes: List[str] = []

        for hc in hole_candidates:
            region_id = self._resolve_region(
                hc["entity_ids"], entity_to_region
            )
            if region_id:
                hole_region_map.setdefault(region_id, []).append(
                    hc["candidate_id"]
                )
            else:
                unassigned_holes.append(hc["candidate_id"])

        # Assign slot candidates to regions
        slot_region_map: Dict[str, List[str]] = {}
        unassigned_slots: List[str] = []

        for sc in slot_candidates:
            eid = sc.get("entity_id")
            # Handle both single entity_id (string) and multi-entity (list)
            if isinstance(eid, list):
                region_id = self._resolve_region(eid, entity_to_region)
            else:
                region_id = entity_to_region.get(eid)
            
            if region_id:
                slot_region_map.setdefault(region_id, []).append(
                    sc["candidate_id"]
                )
            else:
                unassigned_slots.append(sc["candidate_id"])

        # Assign radial patterns to regions
        pattern_region_map: Dict[str, List[str]] = {}
        unassigned_patterns: List[str] = []

        for rp in radial_patterns:
            # Resolve via member candidates' entity_ids
            member_ids = rp.get("member_candidate_ids", [])
            # Find entity_ids from hole candidates
            member_entity_ids: List[str] = []
            for hc in hole_candidates:
                if hc["candidate_id"] in member_ids:
                    member_entity_ids.extend(hc["entity_ids"])

            region_id = self._resolve_region(
                member_entity_ids, entity_to_region
            )
            if region_id:
                pattern_region_map.setdefault(region_id, []).append(
                    rp["pattern_id"]
                )
            else:
                unassigned_patterns.append(rp["pattern_id"])

        # Build feature_regions output
        all_region_ids: Set[str] = set()
        all_region_ids.update(hole_region_map.keys())
        all_region_ids.update(slot_region_map.keys())
        all_region_ids.update(pattern_region_map.keys())

        feature_regions: List[Dict] = []
        for rid in sorted(all_region_ids):
            holes = hole_region_map.get(rid, [])
            slots = slot_region_map.get(rid, [])
            patterns = pattern_region_map.get(rid, [])

            feature_regions.append({
                "region_id": rid,
                "hole_candidate_ids": holes,
                "slot_candidate_ids": slots,
                "radial_pattern_ids": patterns,
                "total_candidates": len(holes) + len(slots) + len(patterns),
            })

        total_assigned = sum(fr["total_candidates"] for fr in feature_regions)
        total_unassigned = (
            len(unassigned_holes) +
            len(unassigned_slots) +
            len(unassigned_patterns)
        )

        logger.info(
            f"FeatureRegionGrouper: "
            f"feature_regions={len(feature_regions)} "
            f"assigned={total_assigned} "
            f"unassigned={total_unassigned}"
        )

        return {
            "feature_regions": feature_regions,
            "unassigned_candidates": {
                "holes": unassigned_holes,
                "slots": unassigned_slots,
                "patterns": unassigned_patterns,
            },
            "statistics": {
                "total_feature_regions": len(feature_regions),
                "total_assigned_candidates": total_assigned,
                "total_unassigned_candidates": total_unassigned,
            },
        }

    def _resolve_region(
        self,
        entity_ids: List[str],
        entity_to_region: Dict[str, str],
    ) -> str | None:
        """
        Resolve the region for a set of entity_ids.
        Returns the region_id if all entities belong to the same region.
        Returns None if ambiguous or unresolvable.
        """
        regions_found: Set[str] = set()
        for eid in entity_ids:
            rid = entity_to_region.get(eid)
            if rid:
                regions_found.add(rid)

        if len(regions_found) == 1:
            return regions_found.pop()

        # Ambiguous or no region — do not force
        return None
