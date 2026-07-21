"""
Contour Hierarchy — deterministic geometric containment analysis.

Detects which closed polyline contours contain other contours
using a two-stage guard:
  Stage 1: bounding-box containment (fast O(n²) pre-filter)
  Stage 2: centroid-in-polygon ray-cast (eliminates false positives
           from L/U-shaped outer profiles whose bbox overlaps their notch)

Assigns geometric roles:
  - outer: not contained by any other contour
  - inner: contained within another contour
  - isolated: not closed or not participating

Does NOT infer manufacturing meaning (pocket, cutout, etc.)
Only: geometric containment relationships.
"""
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def _point_in_polygon(px: float, py: float, polygon: List[List[float]]) -> bool:
    """
    Standard horizontal ray-cast point-in-polygon test (Jordan curve theorem).

    Returns True if (px, py) is strictly inside the polygon.
    Boundary edge cases (point exactly on edge) return False — treated as outside
    to avoid ambiguity in containment decisions.

    Args:
        px, py: test point coordinates
        polygon: list of [x, y] vertex pairs (closed or open — last edge auto-closed)

    Returns:
        True if the point is inside the polygon
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    xj, yj = polygon[-1][0], polygon[-1][1]

    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        # Ray crosses edge if one vertex is above py and the other is below
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi) + xi
        ):
            inside = not inside
        xj, yj = xi, yi

    return inside


class ContourHierarchy:
    """
    Detect deterministic contour containment relationships.

    Uses two-stage containment test:
    1. Bounding-box containment (fast pre-filter)
    2. Centroid-in-polygon ray-cast (accuracy guard for non-convex parents)
    """

    def _get_loop_polygon_and_bbox(
        self,
        entity_ids: List[str],
        entity_by_id: Dict[str, Dict],
    ) -> Optional[Dict[str, Any]]:
        import math
        points = []
        for eid in entity_ids:
            ent = entity_by_id.get(eid)
            if not ent:
                continue
            etype = ent.get("entity_type")
            geom = ent.get("geometry", {})
            if etype == "LINE":
                start = geom.get("start")
                end = geom.get("end")
                if start: points.append(start)
                if end: points.append(end)
            elif etype in ("POLYLINE", "LWPOLYLINE"):
                pts = geom.get("points", [])
                points.extend(pts)
            elif etype == "CIRCLE":
                center = geom.get("center")
                radius = geom.get("radius")
                if center and radius:
                    for angle in range(0, 360, 22):
                        rad = math.radians(angle)
                        points.append([center[0] + radius * math.cos(rad), center[1] + radius * math.sin(rad)])
            elif etype == "ARC":
                center = geom.get("center")
                radius = geom.get("radius")
                start_angle = geom.get("start_angle")
                end_angle = geom.get("end_angle")
                if center and radius and start_angle is not None and end_angle is not None:
                    s_ang = start_angle
                    e_ang = end_angle
                    if e_ang < s_ang:
                        e_ang += 360.0
                    for step in range(5):
                        angle_deg = s_ang + (e_ang - s_ang) * step / 4.0
                        rad = math.radians(angle_deg)
                        points.append([center[0] + radius * math.cos(rad), center[1] + radius * math.sin(rad)])
                        
        if not points:
            return None
            
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        
        return {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "area": (xmax - xmin) * (ymax - ymin),
            "polygon": points,
            "centroid_x": cx,
            "centroid_y": cy
        }

    def analyze(
        self,
        entities: List[Dict],
        loops: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Build contour hierarchy from closed polyline entities and loops.

        Returns:
            {
                "hierarchy": [
                    {
                        "entity_id": str,
                        "contour_role": "outer" | "inner" | "isolated",
                        "parent_id": str | None,
                        "children_ids": [...],
                        "nesting_depth": int,
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"ContourHierarchy: analyzing {len(entities)} entities and {len(loops) if loops else 0} loops"
        )

        entity_by_id = {e["entity_id"]: e for e in entities}
        contours = []
        for entity in entities:
            etype = entity.get("entity_type", "")
            geom = entity.get("geometry", {})

            import math
            if etype in ("POLYLINE", "LWPOLYLINE"):
                if not geom.get("closed", False):
                    continue
                points = geom.get("points", [])
                if len(points) < 3:
                    continue
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                polygon = [[p[0], p[1]] for p in points]
                area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            elif etype == "CIRCLE":
                center = geom.get("center")
                radius = geom.get("radius")
                if not center or radius is None or radius <= 0:
                    continue
                cx, cy = center[0], center[1]
                xs = [cx - radius, cx + radius]
                ys = [cy - radius, cy + radius]
                polygon = []
                for angle in range(0, 360, 22):
                    rad = math.radians(angle)
                    polygon.append([cx + radius * math.cos(rad), cy + radius * math.sin(rad)])
                area = math.pi * radius * radius
            else:
                continue

            contours.append({
                "entity_id": entity["entity_id"],
                "xmin": min(xs),
                "xmax": max(xs),
                "ymin": min(ys),
                "ymax": max(ys),
                "area": area,
                "polygon": polygon,
                "centroid_x": cx,
                "centroid_y": cy,
            })

        if loops:
            for loop in loops:
                loop_ent_ids = loop.get("entity_ids", [])
                if len(loop_ent_ids) <= 1:
                    continue
                loop_data = self._get_loop_polygon_and_bbox(loop_ent_ids, entity_by_id)
                if loop_data:
                    contours.append({
                        "entity_id": loop["loop_id"],
                        **loop_data
                    })

        if not contours:
            return {
                "hierarchy": [],
                "statistics": {"total_contours": 0, "outer": 0, "inner": 0},
            }

        # Sort by area descending (larger contours are potential parents)
        contours.sort(key=lambda c: c["area"], reverse=True)

        # Determine containment: for each contour, find smallest parent
        hierarchy: Dict[str, Dict] = {}
        for c in contours:
            hierarchy[c["entity_id"]] = {
                "entity_id": c["entity_id"],
                "contour_role": "outer",
                "parent_id": None,
                "children_ids": [],
                "nesting_depth": 0,
            }

        bbox_candidates = 0
        centroid_rejections = 0

        for i in range(len(contours)):
            child = contours[i]
            best_parent: Optional[str] = None
            best_area = float("inf")

            for j in range(len(contours)):
                if i == j:
                    continue
                parent = contours[j]

                # Stage 1: bounding-box containment pre-filter (fast)
                if not (
                    parent["xmin"] <= child["xmin"] and
                    parent["xmax"] >= child["xmax"] and
                    parent["ymin"] <= child["ymin"] and
                    parent["ymax"] >= child["ymax"] and
                    parent["area"] > child["area"]
                ):
                    continue

                bbox_candidates += 1

                # Stage 2: centroid-in-polygon guard (accuracy)
                # The child's centroid must lie inside the parent's actual polygon.
                # This rejects false positives from L/U-shaped outer profiles
                # whose bounding box covers the concave notch area.
                if not str(parent["entity_id"]).startswith("loop_"):
                    if not _point_in_polygon(
                        child["centroid_x"],
                        child["centroid_y"],
                        parent["polygon"],
                    ):
                        centroid_rejections += 1
                        logger.debug(
                            f"Centroid rejection: child {child['entity_id']} centroid "
                            f"({child['centroid_x']:.3f}, {child['centroid_y']:.3f}) "
                            f"is outside parent {parent['entity_id']} polygon"
                        )
                        continue

                if parent["area"] < best_area:
                    best_area = parent["area"]
                    best_parent = parent["entity_id"]

            if best_parent is not None:
                hierarchy[child["entity_id"]]["parent_id"] = best_parent
                hierarchy[child["entity_id"]]["contour_role"] = "inner"
                hierarchy[best_parent]["children_ids"].append(child["entity_id"])

        # Compute nesting depth
        for eid, node in hierarchy.items():
            depth = 0
            current = eid
            while hierarchy[current]["parent_id"] is not None:
                depth += 1
                current = hierarchy[current]["parent_id"]
                if depth > 10:  # Safety cap
                    break
            node["nesting_depth"] = depth

        result_list = list(hierarchy.values())
        outer_count = sum(1 for h in result_list if h["contour_role"] == "outer")
        inner_count = sum(1 for h in result_list if h["contour_role"] == "inner")

        logger.info(
            f"ContourHierarchy: contours={len(result_list)} "
            f"outer={outer_count} inner={inner_count} "
            f"bbox_candidates={bbox_candidates} centroid_rejections={centroid_rejections}"
        )

        return {
            "hierarchy": result_list,
            "statistics": {
                "total_contours": len(result_list),
                "outer": outer_count,
                "inner": inner_count,
                "bbox_candidates": bbox_candidates,
                "centroid_rejections": centroid_rejections,
            },
        }
