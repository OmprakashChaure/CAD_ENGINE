"""
Relationship Confidence Manager — organize deterministic relationship confidence.

Evaluates structural relationships and assigns confidence scores based on:
  - Number of reinforcing structural signals
  - Topology consistency between related candidates
  - Ambiguity overlap between candidates

Confidence reflects structural consistency ONLY.
NOT engineering certainty. NOT semantic probability.

Preserves:
  - Conservative confidence behavior
  - Ambiguity propagation
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


class RelationshipConfidenceManager:
    """
    Assign confidence scores to candidate relationships.

    Scoring factors:
      - same_region: base 0.5 (structural proximity)
      - pattern_member: base 0.7 (geometric regularity)
      - repetition_sibling: base 0.6 (signature match)
      - Multiple reinforcing relationships increase confidence
    """

    def evaluate(
        self,
        relationships: List[Dict],
        confidence_scores: List[Dict],
    ) -> Dict[str, Any]:
        """
        Assign confidence to each relationship.

        Args:
            relationships: from CandidateRelationshipBuilder
            confidence_scores: from CandidateConfidenceAnalyzer

        Returns:
            {
                "scored_relationships": [
                    {
                        "source_candidate_id": str,
                        "target_candidate_id": str,
                        "relationship_type": str,
                        "relationship_confidence": float,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"RelationshipConfidenceManager: "
            f"evaluating {len(relationships)} relationships"
        )

        # Build candidate confidence lookup
        conf_lookup: Dict[str, float] = {}
        for cs in confidence_scores:
            conf_lookup[cs["candidate_id"]] = cs["structural_confidence"]

        # Base confidence by relationship type
        type_base = {
            "same_region": 0.5,
            "pattern_member": 0.7,
            "repetition_sibling": 0.6,
            "concentric_association": 0.65,
        }

        scored: List[Dict] = []

        for rel in relationships:
            rel_type = rel["relationship_type"]
            src = rel["source_candidate_id"]
            tgt = rel["target_candidate_id"]

            # Base from relationship type
            base = type_base.get(rel_type, 0.4)

            # Modulate by participant confidence (average)
            src_conf = conf_lookup.get(src, 0.5)
            tgt_conf = conf_lookup.get(tgt, 0.5)
            avg_participant = (src_conf + tgt_conf) / 2.0

            # Final: weighted combination
            rel_confidence = round(
                0.6 * base + 0.4 * avg_participant, 3
            )

            scored.append({
                "source_candidate_id": src,
                "target_candidate_id": tgt,
                "relationship_type": rel_type,
                "relationship_confidence": rel_confidence,
            })

        # Statistics
        if scored:
            confs = [s["relationship_confidence"] for s in scored]
            avg = sum(confs) / len(confs)
            high = sum(1 for c in confs if c >= 0.6)
            low = sum(1 for c in confs if c < 0.4)
        else:
            avg = 0.0
            high = low = 0

        logger.info(
            f"RelationshipConfidenceManager: "
            f"scored={len(scored)} avg={avg:.3f} "
            f"high={high} low={low}"
        )

        return {
            "scored_relationships": scored,
            "statistics": {
                "total_scored": len(scored),
                "average_confidence": round(avg, 3),
                "high_confidence_relationships": high,
                "low_confidence_relationships": low,
            },
        }
