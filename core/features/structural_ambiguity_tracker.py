"""
Structural Ambiguity Tracker — explicitly preserve engineering uncertainty.

Tracks candidates with low confidence, conflicting interpretations,
or partial structural evidence. Ambiguity is NOT failure —
it is required metadata for future ML interpretation.

Produces:
  - Ambiguity records (candidates with unresolved structural status)
  - Ambiguity classification

Preserves:
  - Future interpretability
  - All competing structural hypotheses
  - Entity lineage
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)

# Confidence threshold below which a candidate is considered ambiguous
AMBIGUITY_THRESHOLD = 0.5


class StructuralAmbiguityTracker:
    """
    Explicitly preserve and track engineering structural uncertainty.

    Collects:
      - Low-confidence candidates
      - Conflicted entities
      - Partial structural evidence

    Ambiguity preservation is REQUIRED for future ML training quality.
    """

    def __init__(self, threshold: float = AMBIGUITY_THRESHOLD):
        self.threshold = threshold

    def track(
        self,
        confidence_result: Dict[str, Any],
        conflict_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Track structural ambiguity across the candidate system.

        Returns:
            {
                "ambiguous_candidates": [
                    {
                        "candidate_id": str,
                        "ambiguity_reason": str,
                        "structural_confidence": float,
                        "conflict_count": int,
                    }
                ],
                "ambiguity_summary": {
                    "total_ambiguous": int,
                    "by_reason": { ... },
                },
                "statistics": { ... }
            }
        """
        logger.info("Tracking structural ambiguity")

        ambiguous: List[Dict] = []

        # Low-confidence candidates
        confidence_scores = confidence_result.get(
            "confidence_scores", []
        )

        low_conf_ids = set()
        for score in confidence_scores:
            if score["structural_confidence"] < self.threshold:
                ambiguous.append({
                    "candidate_id": score["candidate_id"],
                    "ambiguity_reason": "low_structural_confidence",
                    "structural_confidence": score["structural_confidence"],
                    "conflict_count": 0,
                })
                low_conf_ids.add(score["candidate_id"])

        # Conflicted entities — find which candidates are involved
        conflicts = conflict_result.get("conflicts", [])
        conflicted_candidate_ids: Dict[str, int] = {}

        for conflict in conflicts:
            for cid in conflict.get("claiming_candidates", []):
                conflicted_candidate_ids[cid] = (
                    conflicted_candidate_ids.get(cid, 0) + 1
                )

        for cid, count in conflicted_candidate_ids.items():
            if cid not in low_conf_ids:
                # Find its confidence
                conf_val = 0.0
                for score in confidence_scores:
                    if score["candidate_id"] == cid:
                        conf_val = score["structural_confidence"]
                        break

                ambiguous.append({
                    "candidate_id": cid,
                    "ambiguity_reason": "entity_conflict",
                    "structural_confidence": conf_val,
                    "conflict_count": count,
                })

        # Classify by reason
        by_reason: Dict[str, int] = {}
        for a in ambiguous:
            reason = a["ambiguity_reason"]
            by_reason[reason] = by_reason.get(reason, 0) + 1

        total_candidates = len(confidence_scores)
        ambiguous_ratio = (
            len(ambiguous) / total_candidates
            if total_candidates > 0 else 0.0
        )

        logger.info(
            f"AmbiguityTracker: ambiguous={len(ambiguous)} "
            f"ratio={ambiguous_ratio:.2f} "
            f"reasons={by_reason}"
        )

        return {
            "ambiguous_candidates": ambiguous,
            "ambiguity_summary": {
                "total_ambiguous": len(ambiguous),
                "by_reason": by_reason,
                "ambiguity_ratio": round(ambiguous_ratio, 3),
            },
            "statistics": {
                "total_ambiguous": len(ambiguous),
                "total_candidates_analyzed": total_candidates,
                "ambiguity_threshold": self.threshold,
                "ambiguity_ratio": round(ambiguous_ratio, 3),
            },
        }
