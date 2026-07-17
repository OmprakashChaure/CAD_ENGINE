"""
Candidate Confidence Analyzer — deterministic structural confidence levels.

Assigns confidence scores to feature candidates based on:
  - Topology consistency (shared vertices, adjacency)
  - Geometric regularity (radius uniformity, spacing)
  - Structural repetition (pattern membership)
  - Contour completeness (closed vs open)

Confidence represents STRUCTURAL consistency only.
NOT semantic certainty. NOT manufacturing probability.

Preserves:
  - Uncertainty visibility
  - Deterministic traceability
  - Topology lineage
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


class CandidateConfidenceAnalyzer:
    """
    Assign deterministic structural confidence to feature candidates.

    Confidence scale: 0.0 (ambiguous) to 1.0 (structurally certain)

    Factors:
      - Geometric completeness
      - Pattern membership
      - Topology connectivity
      - Regularity metrics
    """

    def analyze(
        self,
        feature_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute confidence for all feature candidates.

        Returns:
            {
                "confidence_scores": [
                    {
                        "candidate_id": str,
                        "candidate_type": str,
                        "structural_confidence": float,
                        "confidence_factors": { ... },
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info("Analyzing candidate confidence")

        scores: List[Dict] = []

        # Hole candidates
        hole_candidates = feature_result.get(
            "hole_candidates", {}
        ).get("hole_candidates", [])

        for hc in hole_candidates:
            conf, factors = self._score_hole_candidate(hc)
            scores.append({
                "candidate_id": hc["candidate_id"],
                "candidate_type": "hole",
                "structural_confidence": conf,
                "confidence_factors": factors,
            })

        # Slot candidates
        slot_candidates = feature_result.get(
            "slot_candidates", {}
        ).get("slot_candidates", [])

        for sc in slot_candidates:
            conf, factors = self._score_slot_candidate(sc)
            scores.append({
                "candidate_id": sc["candidate_id"],
                "candidate_type": "slot",
                "structural_confidence": conf,
                "confidence_factors": factors,
            })

        # Radial patterns
        radial_patterns = feature_result.get(
            "radial_patterns", {}
        ).get("radial_patterns", [])

        for rp in radial_patterns:
            conf, factors = self._score_radial_pattern(rp)
            scores.append({
                "candidate_id": rp["pattern_id"],
                "candidate_type": "radial_pattern",
                "structural_confidence": conf,
                "confidence_factors": factors,
            })

        # Statistics
        if scores:
            confs = [s["structural_confidence"] for s in scores]
            avg_conf = sum(confs) / len(confs)
            high = sum(1 for c in confs if c >= 0.7)
            medium = sum(1 for c in confs if 0.4 <= c < 0.7)
            low = sum(1 for c in confs if c < 0.4)
        else:
            avg_conf = 0.0
            high = medium = low = 0

        logger.info(
            f"ConfidenceAnalyzer: scored={len(scores)} "
            f"avg={avg_conf:.2f} high={high} med={medium} low={low}"
        )

        return {
            "confidence_scores": scores,
            "statistics": {
                "total_scored": len(scores),
                "average_confidence": round(avg_conf, 3),
                "high_confidence": high,
                "medium_confidence": medium,
                "low_confidence": low,
            },
        }

    def _score_hole_candidate(self, hc: Dict) -> tuple:
        """Score a hole candidate based on structural factors."""
        factors = {}
        score = 0.5  # Base

        # Multi-radius systems are more structurally certain
        radius_count = hc.get("radius_count", 1)
        if radius_count >= 2:
            factors["multi_radius"] = True
            score += 0.2
        else:
            factors["multi_radius"] = False

        # Single isolated circle — lower structural certainty
        if radius_count == 1:
            factors["isolated_circle"] = True
            score -= 0.1

        return round(min(max(score, 0.0), 1.0), 3), factors

    def _score_slot_candidate(self, sc: Dict) -> tuple:
        """Score a slot candidate based on structural factors."""
        factors = {}
        score = 0.4  # Base (slots are less certain structurally)

        aspect = sc.get("aspect_ratio", 1.0)

        # Higher aspect ratio = more structurally slot-like
        if aspect >= 4.0:
            factors["high_aspect"] = True
            score += 0.2
        elif aspect >= 2.5:
            factors["moderate_aspect"] = True
            score += 0.1

        # Closed contour adds certainty
        if sc.get("is_closed", False):
            factors["closed_contour"] = True
            score += 0.1

        return round(min(max(score, 0.0), 1.0), 3), factors

    def _score_radial_pattern(self, rp: Dict) -> tuple:
        """Score a radial pattern based on structural factors."""
        factors = {}
        score = 0.6  # Base (patterns are structurally strong)

        count = rp.get("member_count", 0)
        spacing = rp.get("angular_spacing_deg")

        # More members = higher confidence
        if count >= 6:
            factors["high_member_count"] = True
            score += 0.2
        elif count >= 4:
            factors["moderate_member_count"] = True
            score += 0.1

        # Equal angular spacing confirmed
        if spacing is not None:
            factors["equal_spacing_confirmed"] = True
            score += 0.1

        return round(min(max(score, 0.0), 1.0), 3), factors
