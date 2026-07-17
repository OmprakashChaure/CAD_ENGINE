"""
Contextual Ambiguity Propagator — preserve ambiguity across relationship systems.

Propagates ambiguity from individual candidates into their relationships
and clusters. Prevents forced certainty escalation.

Ambiguity propagation is REQUIRED behavior — not a failure condition.

Preserves:
  - Future interpretability
  - All competing structural hypotheses
  - Conservative confidence behavior
"""
from typing import Any, Dict, List, Set

from utils.logger import get_logger

logger = get_logger(__name__)


class ContextualAmbiguityPropagator:
    """
    Propagate ambiguity across candidate relationship systems.

    Rules:
      - If a candidate is ambiguous, its relationships inherit uncertainty
      - If both sides of a relationship are ambiguous, the relationship
        is marked as structurally uncertain
      - Clusters containing ambiguous candidates are flagged

    Prevents:
      - Forced certainty escalation
      - Ambiguity collapse
      - Semantic overreach
    """

    def propagate(
        self,
        scored_relationships: List[Dict],
        ambiguity_result: Dict[str, Any],
        clusters: List[Dict],
    ) -> Dict[str, Any]:
        """
        Propagate ambiguity into relationships and clusters.

        Args:
            scored_relationships: from RelationshipConfidenceManager
            ambiguity_result: from StructuralAmbiguityTracker
            clusters: from ContextClusterAnalyzer

        Returns:
            {
                "ambiguous_relationships": [
                    {
                        "source_candidate_id": str,
                        "target_candidate_id": str,
                        "ambiguity_source": str,
                    }
                ],
                "ambiguous_clusters": [
                    {
                        "cluster_id": str,
                        "ambiguous_member_count": int,
                        "cluster_ambiguity_ratio": float,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info("Propagating contextual ambiguity")

        # Build set of ambiguous candidate IDs
        ambiguous_ids: Set[str] = set()
        for ac in ambiguity_result.get("ambiguous_candidates", []):
            ambiguous_ids.add(ac["candidate_id"])

        # Propagate into relationships
        ambiguous_rels: List[Dict] = []

        for rel in scored_relationships:
            src = rel["source_candidate_id"]
            tgt = rel["target_candidate_id"]

            src_ambiguous = src in ambiguous_ids
            tgt_ambiguous = tgt in ambiguous_ids

            if src_ambiguous and tgt_ambiguous:
                ambiguous_rels.append({
                    "source_candidate_id": src,
                    "target_candidate_id": tgt,
                    "ambiguity_source": "both_candidates_ambiguous",
                })
            elif src_ambiguous:
                ambiguous_rels.append({
                    "source_candidate_id": src,
                    "target_candidate_id": tgt,
                    "ambiguity_source": "source_ambiguous",
                })
            elif tgt_ambiguous:
                ambiguous_rels.append({
                    "source_candidate_id": src,
                    "target_candidate_id": tgt,
                    "ambiguity_source": "target_ambiguous",
                })

        # Propagate into clusters
        ambiguous_clusters: List[Dict] = []

        for cluster in clusters:
            members = cluster.get("candidate_ids", [])
            amb_count = sum(1 for m in members if m in ambiguous_ids)

            if amb_count > 0:
                ratio = amb_count / len(members) if members else 0.0
                ambiguous_clusters.append({
                    "cluster_id": cluster["cluster_id"],
                    "ambiguous_member_count": amb_count,
                    "cluster_ambiguity_ratio": round(ratio, 3),
                })

        total_rels = len(scored_relationships)
        amb_rel_ratio = (
            len(ambiguous_rels) / total_rels if total_rels > 0 else 0.0
        )

        logger.info(
            f"AmbiguityPropagator: "
            f"ambiguous_rels={len(ambiguous_rels)}/{total_rels} "
            f"ambiguous_clusters={len(ambiguous_clusters)}/{len(clusters)}"
        )

        return {
            "ambiguous_relationships": ambiguous_rels,
            "ambiguous_clusters": ambiguous_clusters,
            "statistics": {
                "total_ambiguous_relationships": len(ambiguous_rels),
                "total_relationships": total_rels,
                "ambiguous_relationship_ratio": round(amb_rel_ratio, 3),
                "total_ambiguous_clusters": len(ambiguous_clusters),
                "total_clusters": len(clusters),
            },
        }
