"""
Candidate Relationship Builder — deterministic structural candidate relationships.

Builds relationships between feature candidates based on:
  - Shared region membership
  - Concentric association
  - Radial pattern membership
  - Repetition group membership

Relationships represent structural association ONLY.
NOT engineering function. NOT manufacturing dependency.

Preserves:
  - Ambiguity
  - Topology lineage
  - Candidate lineage
"""
from typing import Any, Dict, List, Set
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class CandidateRelationshipBuilder:
    """
    Build deterministic structural relationships between candidates.

    Relationship types (structural only):
      - same_region: candidates in the same topology region
      - concentric_association: candidates sharing concentric group
      - pattern_member: candidates in the same radial pattern
      - repetition_sibling: candidates with identical geometry signature
    """

    def build(
        self,
        feature_result: Dict[str, Any],
        refinement_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build candidate relationship graph.

        Returns:
            {
                "relationships": [
                    {
                        "source_candidate_id": str,
                        "target_candidate_id": str,
                        "relationship_type": str,
                        "context": str,
                    }
                ],
                "adjacency": { candidate_id: [related_candidate_ids] },
                "statistics": { ... }
            }
        """
        logger.info("Building candidate relationships")

        relationships: List[Dict] = []
        seen_pairs: Set[tuple] = set()

        def add_rel(src: str, tgt: str, rel_type: str, context: str = ""):
            pair = (min(src, tgt), max(src, tgt), rel_type)
            if pair in seen_pairs:
                return
            seen_pairs.add(pair)
            relationships.append({
                "source_candidate_id": src,
                "target_candidate_id": tgt,
                "relationship_type": rel_type,
                "context": context,
            })

        # Same-region relationships from feature_regions
        feature_regions = feature_result.get(
            "feature_regions", {}
        ).get("feature_regions", [])

        for fr in feature_regions:
            all_ids = (
                fr.get("hole_candidate_ids", []) +
                fr.get("slot_candidate_ids", []) +
                fr.get("radial_pattern_ids", [])
            )
            for i in range(len(all_ids)):
                for j in range(i + 1, len(all_ids)):
                    add_rel(
                        all_ids[i], all_ids[j],
                        "same_region",
                        fr["region_id"],
                    )

        # Pattern membership relationships
        radial_patterns = feature_result.get(
            "radial_patterns", {}
        ).get("radial_patterns", [])

        for rp in radial_patterns:
            members = rp.get("member_candidate_ids", [])
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    add_rel(
                        members[i], members[j],
                        "pattern_member",
                        rp["pattern_id"],
                    )

        # Repetition sibling relationships
        repetitions = refinement_result.get(
            "repetitions", {}
        ).get("repetition_groups", [])

        for rep in repetitions:
            siblings = rep.get("candidate_ids", [])
            for i in range(len(siblings)):
                for j in range(i + 1, len(siblings)):
                    add_rel(
                        siblings[i], siblings[j],
                        "repetition_sibling",
                        rep["group_id"],
                    )

        # Build adjacency list
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for rel in relationships:
            adjacency[rel["source_candidate_id"]].add(rel["target_candidate_id"])
            adjacency[rel["target_candidate_id"]].add(rel["source_candidate_id"])

        adjacency_sorted = {
            k: sorted(list(v)) for k, v in adjacency.items()
        }

        # Statistics by type
        type_counts: Dict[str, int] = defaultdict(int)
        for rel in relationships:
            type_counts[rel["relationship_type"]] += 1

        logger.info(
            f"CandidateRelationshipBuilder: "
            f"relationships={len(relationships)} "
            f"connected_candidates={len(adjacency_sorted)} "
            f"types={dict(type_counts)}"
        )

        return {
            "relationships": relationships,
            "adjacency": adjacency_sorted,
            "statistics": {
                "total_relationships": len(relationships),
                "connected_candidates": len(adjacency_sorted),
                "by_type": dict(type_counts),
            },
        }
