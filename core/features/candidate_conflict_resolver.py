"""
Candidate Conflict Resolver — detect overlapping or conflicting candidates.

Identifies entities claimed by multiple feature candidates simultaneously.
Does NOT aggressively resolve ambiguity — preserves it explicitly.

Ambiguous geometry is VALID engineering data.

Produces:
  - Conflict groups (entities shared across candidates)
  - Conflict severity indicators

Preserves:
  - All competing interpretations
  - Ambiguity metadata
  - Entity lineage
"""
from typing import Any, Dict, List, Set
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)


class CandidateConflictResolver:
    """
    Detect overlapping structural candidate claims.

    An entity may be claimed by multiple candidates (e.g., a circle
    that is both part of a concentric group AND a radial pattern).
    This is NOT an error — it is structural ambiguity.

    Does NOT force resolution. Preserves all interpretations.
    """

    def detect(
        self,
        feature_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Detect entity-level conflicts between candidates.

        Returns:
            {
                "conflicts": [
                    {
                        "entity_id": str,
                        "claiming_candidates": [...],
                        "claim_count": int,
                        "severity": "low" | "medium" | "high",
                    }
                ],
                "conflict_free_entities": int,
                "statistics": { ... }
            }
        """
        logger.info("Detecting candidate conflicts")

        # Build entity_id → list of claiming candidate_ids
        entity_claims: Dict[str, List[str]] = defaultdict(list)

        # Hole candidates
        hole_candidates = feature_result.get(
            "hole_candidates", {}
        ).get("hole_candidates", [])

        for hc in hole_candidates:
            for eid in hc.get("entity_ids", []):
                entity_claims[eid].append(hc["candidate_id"])

        # Slot candidates
        slot_candidates = feature_result.get(
            "slot_candidates", {}
        ).get("slot_candidates", [])

        for sc in slot_candidates:
            eid = sc.get("entity_id")
            if eid:
                # Handle both single entity_id (string) and multi-entity (list)
                if isinstance(eid, list):
                    for e in eid:
                        entity_claims[e].append(sc["candidate_id"])
                else:
                    entity_claims[eid].append(sc["candidate_id"])

        # Radial pattern members (via hole candidates)
        radial_patterns = feature_result.get(
            "radial_patterns", {}
        ).get("radial_patterns", [])

        for rp in radial_patterns:
            # Pattern itself claims its member candidates' entities
            member_ids = rp.get("member_candidate_ids", [])
            for hc in hole_candidates:
                if hc["candidate_id"] in member_ids:
                    for eid in hc.get("entity_ids", []):
                        entity_claims[eid].append(rp["pattern_id"])

        # Identify conflicts (entities with 2+ claims)
        conflicts: List[Dict] = []
        conflict_free = 0

        for eid, claims in entity_claims.items():
            unique_claims = list(set(claims))
            if len(unique_claims) >= 2:
                severity = self._classify_severity(len(unique_claims))
                conflicts.append({
                    "entity_id": eid,
                    "claiming_candidates": unique_claims,
                    "claim_count": len(unique_claims),
                    "severity": severity,
                })
            else:
                conflict_free += 1

        high = sum(1 for c in conflicts if c["severity"] == "high")
        medium = sum(1 for c in conflicts if c["severity"] == "medium")
        low = sum(1 for c in conflicts if c["severity"] == "low")

        logger.info(
            f"ConflictResolver: conflicts={len(conflicts)} "
            f"(high={high} med={medium} low={low}) "
            f"conflict_free={conflict_free}"
        )

        return {
            "conflicts": conflicts,
            "conflict_free_entities": conflict_free,
            "statistics": {
                "total_conflicts": len(conflicts),
                "high_severity": high,
                "medium_severity": medium,
                "low_severity": low,
                "conflict_free_entities": conflict_free,
                "total_claimed_entities": len(entity_claims),
            },
        }

    def _classify_severity(self, claim_count: int) -> str:
        """Classify conflict severity by number of competing claims."""
        if claim_count >= 4:
            return "high"
        elif claim_count >= 3:
            return "medium"
        return "low"
