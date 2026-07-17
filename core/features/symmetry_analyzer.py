"""
Symmetry Analyzer — detect deterministic structural symmetry.

Identifies mirrored and rotationally repeated geometry structures
using coordinate analysis. Does NOT infer engineering function.

Produces:
  - Bilateral symmetry candidates (mirror pairs)
  - Structural repetition groups

Preserves:
  - Transformation relationships
  - Geometry traceability
  - Entity lineage
"""
import math
from typing import Any, Dict, List, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# Tolerance for coordinate mirroring (absolute)
MIRROR_TOLERANCE = 0.01


class SymmetryAnalyzer:
    """
    Detect deterministic structural symmetry from geometry.

    Analyzes entity positions for bilateral mirror symmetry
    about the drawing's principal axes.

    Does NOT infer engineering function or manufacturing intent.
    """

    def __init__(self, tolerance: float = MIRROR_TOLERANCE):
        self.tolerance = tolerance

    def analyze(
        self,
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """
        Detect symmetry candidates.

        Args:
            entities: canonical entities (post-filtering)

        Returns:
            {
                "symmetry_groups": [
                    {
                        "group_id": "sym_00001",
                        "axis": "vertical" | "horizontal",
                        "axis_position": float,
                        "member_pairs": [[eid_a, eid_b], ...],
                        "pair_count": int,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"SymmetryAnalyzer: analyzing {len(entities)} entities"
        )

        # Extract entities with deterministic center points
        centered = self._extract_centered_entities(entities)

        if len(centered) < 2:
            logger.info("SymmetryAnalyzer: insufficient centered entities")
            return {
                "symmetry_groups": [],
                "statistics": {
                    "total_groups": 0,
                    "entities_analyzed": len(centered),
                },
            }

        # Compute drawing midpoints
        all_x = [c["cx"] for c in centered]
        all_y = [c["cy"] for c in centered]
        mid_x = (min(all_x) + max(all_x)) / 2.0
        mid_y = (min(all_y) + max(all_y)) / 2.0

        groups: List[Dict] = []
        counter = 0

        # Check vertical axis symmetry (mirror about x = mid_x)
        v_pairs = self._find_mirror_pairs(
            centered, axis="vertical", axis_pos=mid_x
        )
        if v_pairs:
            counter += 1
            groups.append({
                "group_id": f"sym_{counter:05d}",
                "axis": "vertical",
                "axis_position": round(mid_x, 4),
                "member_pairs": v_pairs,
                "pair_count": len(v_pairs),
            })

        # Check horizontal axis symmetry (mirror about y = mid_y)
        h_pairs = self._find_mirror_pairs(
            centered, axis="horizontal", axis_pos=mid_y
        )
        if h_pairs:
            counter += 1
            groups.append({
                "group_id": f"sym_{counter:05d}",
                "axis": "horizontal",
                "axis_position": round(mid_y, 4),
                "member_pairs": h_pairs,
                "pair_count": len(h_pairs),
            })

        logger.info(
            f"SymmetryAnalyzer: groups={len(groups)} "
            f"(v_pairs={len(v_pairs)} h_pairs={len(h_pairs)})"
        )

        return {
            "symmetry_groups": groups,
            "statistics": {
                "total_groups": len(groups),
                "vertical_pairs": len(v_pairs),
                "horizontal_pairs": len(h_pairs),
                "entities_analyzed": len(centered),
            },
        }

    def _extract_centered_entities(
        self, entities: List[Dict]
    ) -> List[Dict]:
        """Extract entities with deterministic center coordinates."""
        result = []

        for entity in entities:
            geometry = entity.get("geometry")
            if geometry is None:
                continue

            etype = entity.get("entity_type")
            cx, cy = None, None

            if etype == "CIRCLE" or etype == "ARC":
                center = geometry.get("center")
                if center:
                    cx, cy = center[0], center[1]

            elif etype == "LINE":
                start = geometry.get("start")
                end = geometry.get("end")
                if start and end:
                    cx = (start[0] + end[0]) / 2.0
                    cy = (start[1] + end[1]) / 2.0

            elif etype in ("LWPOLYLINE", "POLYLINE"):
                points = geometry.get("points", [])
                if points:
                    cx = sum(p[0] for p in points) / len(points)
                    cy = sum(p[1] for p in points) / len(points)

            if cx is not None and cy is not None:
                result.append({
                    "entity_id": entity["entity_id"],
                    "entity_type": etype,
                    "cx": cx,
                    "cy": cy,
                    "geometry": geometry,
                })

        return result

    def _find_mirror_pairs(
        self,
        centered: List[Dict],
        axis: str,
        axis_pos: float,
    ) -> List[List[str]]:
        """
        Find entity pairs that are mirrored about the given axis.

        For vertical axis: entities at (axis_pos + d) and (axis_pos - d)
        For horizontal axis: entities at (axis_pos + d) and (axis_pos - d)
        """
        pairs: List[List[str]] = []
        used: set = set()

        for i in range(len(centered)):
            if centered[i]["entity_id"] in used:
                continue

            for j in range(i + 1, len(centered)):
                if centered[j]["entity_id"] in used:
                    continue

                # Must be same entity type
                if centered[i]["entity_type"] != centered[j]["entity_type"]:
                    continue

                a = centered[i]
                b = centered[j]

                is_mirror = False

                if axis == "vertical":
                    # Mirror about x = axis_pos
                    # a.cx and b.cx should be equidistant from axis_pos
                    dist_a = a["cx"] - axis_pos
                    dist_b = b["cx"] - axis_pos
                    if (
                        abs(dist_a + dist_b) < self.tolerance and
                        abs(a["cy"] - b["cy"]) < self.tolerance and
                        abs(dist_a) > self.tolerance  # not on axis
                    ):
                        is_mirror = True

                elif axis == "horizontal":
                    # Mirror about y = axis_pos
                    dist_a = a["cy"] - axis_pos
                    dist_b = b["cy"] - axis_pos
                    if (
                        abs(dist_a + dist_b) < self.tolerance and
                        abs(a["cx"] - b["cx"]) < self.tolerance and
                        abs(dist_a) > self.tolerance
                    ):
                        is_mirror = True

                if is_mirror:
                    pairs.append([a["entity_id"], b["entity_id"]])
                    used.add(a["entity_id"])
                    used.add(b["entity_id"])
                    break

        return pairs
