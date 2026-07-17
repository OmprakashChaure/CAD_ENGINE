"""
Radial Pattern Detector — detect repeated radial geometry organization.

Identifies groups of hole candidates arranged at equal angular spacing
around a common center. Does NOT infer bolt circles or manufacturing intent.

Produces:
  - Radial pattern candidates (repeated angular structures)

Preserves:
  - Angular ordering
  - Radius hierarchy
  - Entity lineage
"""
import math
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)

# Minimum members for a radial pattern
MIN_RADIAL_COUNT = 3

# Tolerance for equal-radius grouping (relative)
RADIUS_TOLERANCE = 0.02

# Tolerance for equal angular spacing (degrees)
ANGLE_TOLERANCE_DEG = 5.0


class RadialPatternDetector:
    """
    Detect repeated radial geometry organization.

    Analyzes hole candidates for circular repetition patterns
    (equal radius from a common center + equal angular spacing).

    Does NOT infer: bolt circles, manufacturing intent.
    Only: radial structural candidates.
    """

    def __init__(
        self,
        min_count: int = MIN_RADIAL_COUNT,
        radius_tol: float = RADIUS_TOLERANCE,
        angle_tol: float = ANGLE_TOLERANCE_DEG,
    ):
        self.min_count = min_count
        self.radius_tol = radius_tol
        self.angle_tol = angle_tol

    def detect(
        self,
        hole_candidates: List[Dict],
    ) -> Dict[str, Any]:
        """
        Detect radial pattern candidates from hole candidates.

        Args:
            hole_candidates: output from HoleCandidateDetector

        Returns:
            {
                "radial_patterns": [
                    {
                        "pattern_id": "rp_00001",
                        "center": [x, y],
                        "pattern_radius": float,
                        "member_candidate_ids": [...],
                        "member_count": int,
                        "angular_spacing_deg": float | None,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"Detecting radial patterns from "
            f"{len(hole_candidates)} hole candidates"
        )

        # Only single-radius candidates participate in radial patterns
        single_candidates = [
            c for c in hole_candidates
            if c["candidate_type"] == "single_radius"
        ]

        if len(single_candidates) < self.min_count:
            logger.info("RadialPatternDetector: insufficient candidates")
            return {
                "radial_patterns": [],
                "statistics": {
                    "total_patterns": 0,
                    "candidates_analyzed": len(single_candidates),
                },
            }

        # Group by similar hole radius
        radius_groups = self._group_by_radius(single_candidates)

        # For each radius group, check for circular arrangement
        patterns: List[Dict] = []
        counter = 0

        for group in radius_groups:
            if len(group) < self.min_count:
                continue

            pattern = self._detect_circular_arrangement(group)
            if pattern is not None:
                counter += 1
                pattern["pattern_id"] = f"rp_{counter:05d}"
                patterns.append(pattern)

        logger.info(
            f"RadialPatternDetector: patterns={len(patterns)}"
        )

        return {
            "radial_patterns": patterns,
            "statistics": {
                "total_patterns": len(patterns),
                "candidates_analyzed": len(single_candidates),
                "radius_groups_found": len(radius_groups),
            },
        }

    def _group_by_radius(
        self, candidates: List[Dict]
    ) -> List[List[Dict]]:
        """Group candidates with similar hole radii."""
        if not candidates:
            return []

        sorted_cands = sorted(
            candidates, key=lambda c: c["radii"][0]
        )

        groups: List[List[Dict]] = []
        current_group = [sorted_cands[0]]

        for i in range(1, len(sorted_cands)):
            r_prev = current_group[0]["radii"][0]
            r_curr = sorted_cands[i]["radii"][0]

            if r_prev > 0 and abs(r_curr - r_prev) / r_prev <= self.radius_tol:
                current_group.append(sorted_cands[i])
            else:
                groups.append(current_group)
                current_group = [sorted_cands[i]]

        groups.append(current_group)
        return groups

    def _detect_circular_arrangement(
        self, group: List[Dict]
    ) -> Dict | None:
        """
        Check if a group of same-radius candidates forms
        a circular arrangement around a common center.
        """
        centers = [c["center"] for c in group]

        # Compute centroid of all centers
        cx = sum(p[0] for p in centers) / len(centers)
        cy = sum(p[1] for p in centers) / len(centers)

        # Compute distance from centroid to each candidate center
        distances = []
        for p in centers:
            d = math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            distances.append(d)

        if not distances or max(distances) == 0:
            return None

        avg_dist = sum(distances) / len(distances)
        if avg_dist <= 0:
            return None

        # Check if all candidates are at similar distance from centroid
        spread = (max(distances) - min(distances)) / avg_dist
        if spread > 0.1:
            # Not arranged on a common circle
            return None

        # Compute angular spacing
        angles = []
        for p in centers:
            angle = math.degrees(math.atan2(p[1] - cy, p[0] - cx))
            angles.append(angle)

        angles_sorted = sorted(angles)
        spacings = [
            angles_sorted[i + 1] - angles_sorted[i]
            for i in range(len(angles_sorted) - 1)
        ]

        # Check for equal angular spacing
        angular_spacing = None
        if spacings:
            avg_spacing = sum(spacings) / len(spacings)
            if avg_spacing > 0:
                is_equal = all(
                    abs(s - avg_spacing) < self.angle_tol
                    for s in spacings
                )
                if is_equal:
                    angular_spacing = round(avg_spacing, 2)

        return {
            "center": [round(cx, 4), round(cy, 4)],
            "pattern_radius": round(avg_dist, 4),
            "member_candidate_ids": [c["candidate_id"] for c in group],
            "member_count": len(group),
            "angular_spacing_deg": angular_spacing,
        }
