"""
Repeated Pattern Consolidator — consolidate repeated structural systems.

Detects groups of feature candidates with identical or near-identical
geometric signatures, indicating structural repetition in the drawing.

Does NOT infer manufacturing templates or engineering function.
Only: deterministic repetition analysis.

Produces:
  - Repetition groups (candidates with matching geometry signatures)
  - Repetition counts

Preserves:
  - Repetition lineage
  - Topology traceability
  - Candidate ownership
"""
from typing import Any, Dict, List, Tuple
from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)

# Precision for signature matching
SIGNATURE_PRECISION = 3


class RepeatedPatternConsolidator:
    """
    Consolidate repeated deterministic structural systems.

    Groups candidates whose geometric signatures match,
    indicating structural repetition (e.g., repeated hole sizes,
    repeated slot dimensions).

    Does NOT infer manufacturing templates.
    """

    def __init__(self, precision: int = SIGNATURE_PRECISION):
        self.precision = precision

    def consolidate(
        self,
        feature_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Detect repeated structural patterns among candidates.

        Returns:
            {
                "repetition_groups": [
                    {
                        "group_id": "rep_00001",
                        "signature": str,
                        "candidate_ids": [...],
                        "repetition_count": int,
                        "candidate_type": str,
                    }
                ],
                "unique_candidates": [...],
                "statistics": { ... }
            }
        """
        logger.info("Consolidating repeated patterns")

        # Build signatures for hole candidates
        hole_signatures: Dict[str, List[str]] = defaultdict(list)
        hole_candidates = feature_result.get(
            "hole_candidates", {}
        ).get("hole_candidates", [])

        for hc in hole_candidates:
            sig = self._hole_signature(hc)
            hole_signatures[sig].append(hc["candidate_id"])

        # Build signatures for slot candidates
        slot_signatures: Dict[str, List[str]] = defaultdict(list)
        slot_candidates = feature_result.get(
            "slot_candidates", {}
        ).get("slot_candidates", [])

        for sc in slot_candidates:
            sig = self._slot_signature(sc)
            slot_signatures[sig].append(sc["candidate_id"])

        # Collect repetition groups (signature with 2+ members)
        groups: List[Dict] = []
        unique: List[str] = []
        counter = 0

        for sig, cids in hole_signatures.items():
            if len(cids) >= 2:
                counter += 1
                groups.append({
                    "group_id": f"rep_{counter:05d}",
                    "signature": sig,
                    "candidate_ids": cids,
                    "repetition_count": len(cids),
                    "candidate_type": "hole",
                })
            else:
                unique.extend(cids)

        for sig, cids in slot_signatures.items():
            if len(cids) >= 2:
                counter += 1
                groups.append({
                    "group_id": f"rep_{counter:05d}",
                    "signature": sig,
                    "candidate_ids": cids,
                    "repetition_count": len(cids),
                    "candidate_type": "slot",
                })
            else:
                unique.extend(cids)

        total_repeated = sum(g["repetition_count"] for g in groups)

        logger.info(
            f"PatternConsolidator: groups={len(groups)} "
            f"repeated_candidates={total_repeated} "
            f"unique={len(unique)}"
        )

        return {
            "repetition_groups": groups,
            "unique_candidates": unique,
            "statistics": {
                "total_repetition_groups": len(groups),
                "total_repeated_candidates": total_repeated,
                "total_unique_candidates": len(unique),
                "max_repetition": max(
                    (g["repetition_count"] for g in groups), default=0
                ),
            },
        }

    def _hole_signature(self, hc: Dict) -> str:
        """Build a deterministic signature for a hole candidate."""
        radii = hc.get("radii", [])
        rounded = tuple(
            round(r, self.precision) for r in sorted(radii)
        )
        return f"hole:{rounded}"

    def _slot_signature(self, sc: Dict) -> str:
        """Build a deterministic signature for a slot candidate."""
        w = round(sc.get("width", 0), self.precision)
        h = round(sc.get("height", 0), self.precision)
        # Normalize: always (smaller, larger)
        dims = tuple(sorted([w, h]))
        return f"slot:{dims}"
