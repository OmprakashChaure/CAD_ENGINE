"""
Slot Candidate Detector — deterministic elongated contour structure detection.

Identifies structural slot candidates from closed polyline geometry
based on aspect ratio analysis. Does NOT assign manufacturing intent.

Produces:
  - Slot-like structural candidates (elongated closed contours)

Preserves:
  - Contour lineage
  - Topology traceability
  - Geometric proportions
"""
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)

# Minimum aspect ratio to consider a closed contour as slot-like
SLOT_ASPECT_THRESHOLD = 2.0


class SlotCandidateDetector:
    """
    Detect deterministic elongated contour structure candidates.

    Analyzes closed LWPOLYLINE/POLYLINE entities for elongated
    proportions that structurally resemble slot-like features.

    Does NOT assume machining intent.
    """

    def __init__(self, aspect_threshold: float = SLOT_ASPECT_THRESHOLD):
        self.aspect_threshold = aspect_threshold

    def detect(
        self,
        entities: List[Dict],
        structural_result: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Detect slot-like structural candidates.
        
        Detects slots from TWO sources:
        1. Closed LWPOLYLINE/POLYLINE entities (single-entity slots)
        2. Closed contours from structural analysis (multi-entity slots like LINE+ARC)

        Returns:
            {
                "slot_candidates": [
                    {
                        "candidate_id": "sc_00001",
                        "entity_id": str or List[str],  # single or multi-entity
                        "aspect_ratio": float,
                        "width": float,
                        "height": float,
                        "center": [x, y],
                        "point_count": int,
                        "is_closed": bool,
                        "source": "polyline" or "contour"
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info("Detecting slot candidates")

        # Compute overall drawing bounding box
        xs_all, ys_all = [], []
        for e in entities:
            geom = e.get("geometry")
            if geom is None:
                continue
            etype = e.get("entity_type")
            if etype == "LINE":
                for pt in (geom.get("start"), geom.get("end")):
                    if pt:
                        xs_all.append(pt[0])
                        ys_all.append(pt[1])
            elif etype == "CIRCLE":
                c = geom.get("center")
                r = geom.get("radius", 0)
                if c:
                    xs_all.extend([c[0] - r, c[0] + r])
                    ys_all.extend([c[1] - r, c[1] + r])
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                for pt in geom.get("points", []):
                    xs_all.append(pt[0])
                    ys_all.append(pt[1])
            elif etype == "ARC":
                c = geom.get("center")
                r = geom.get("radius", 0)
                if c:
                    xs_all.extend([c[0] - r, c[0] + r])
                    ys_all.extend([c[1] - r, c[1] + r])
        
        drawing_area = 0.0
        if xs_all and ys_all:
            drawing_area = (max(xs_all) - min(xs_all)) * (max(ys_all) - min(ys_all))

        # Look up outer contours
        outer_contour_ids = set()
        if structural_result:
            hierarchy_data = structural_result.get("contour_hierarchy", {})
            hierarchy_list = hierarchy_data.get("hierarchy", [])
            for h in hierarchy_list:
                if h.get("contour_role") == "outer":
                    outer_contour_ids.add(h["entity_id"])

        candidates: List[Dict] = []
        counter = 0
        
        # Build entity lookup
        entity_by_id = {e["entity_id"]: e for e in entities}

        # SOURCE 1: Closed LWPOLYLINE/POLYLINE entities
        for entity in entities:
            entity_type = entity.get("entity_type")

            if entity_type not in ("LWPOLYLINE", "POLYLINE"):
                continue

            geometry = entity.get("geometry")
            if geometry is None:
                continue

            # Only closed contours can be slot candidates
            if not geometry.get("closed", False):
                continue

            points = geometry.get("points", [])
            if len(points) < 4:
                continue

            # Compute bounding dimensions
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]

            width = max(xs) - min(xs)
            height = max(ys) - min(ys)

            if width <= 0 or height <= 0:
                continue

            aspect_ratio = max(width, height) / min(width, height)

            # Only elongated contours qualify
            if aspect_ratio < self.aspect_threshold:
                continue

            # Skip root contours or very large contours occupying >80% area
            if entity["entity_id"] in outer_contour_ids:
                continue
            if drawing_area > 0:
                if (width * height) / drawing_area > 0.8:
                    continue

            counter += 1
            center_x = round((min(xs) + max(xs)) / 2, 4)
            center_y = round((min(ys) + max(ys)) / 2, 4)

            candidates.append({
                "candidate_id": f"sc_{counter:05d}",
                "entity_id": entity["entity_id"],
                "aspect_ratio": round(aspect_ratio, 4),
                "width": round(width, 4),
                "height": round(height, 4),
                "center": [center_x, center_y],
                "point_count": len(points),
                "is_closed": True,
                "source": "polyline"
            })
        
        # SOURCE 2: Closed contours from structural analysis (LINE+ARC combinations)
        if structural_result:
            contours_data = structural_result.get("contours", {})
            contours = contours_data.get("contours", [])
            
            for contour in contours:
                if not contour.get("is_closed", False):
                    continue
                
                entity_ids = contour.get("entity_ids", [])
                if len(entity_ids) < 3:  # Need at least 3 entities for a meaningful contour
                    continue
                
                # Collect all geometric points from contour entities
                all_points = []
                for eid in entity_ids:
                    entity = entity_by_id.get(eid)
                    if not entity:
                        continue
                    
                    entity_type = entity.get("entity_type")
                    geom = entity.get("geometry", {})
                    
                    if entity_type == "LINE":
                        start = geom.get("start")
                        end = geom.get("end")
                        if start:
                            all_points.append(start)
                        if end:
                            all_points.append(end)
                    elif entity_type == "ARC":
                        center = geom.get("center")
                        radius = geom.get("radius", 0)
                        if center and radius > 0:
                            # Add arc bounding box points
                            all_points.extend([
                                [center[0] - radius, center[1]],
                                [center[0] + radius, center[1]],
                                [center[0], center[1] - radius],
                                [center[0], center[1] + radius]
                            ])
                    elif entity_type == "CIRCLE":
                        center = geom.get("center")
                        radius = geom.get("radius", 0)
                        if center and radius > 0:
                            # Add circle bounding box
                            all_points.extend([
                                [center[0] - radius, center[1] - radius],
                                [center[0] + radius, center[1] - radius],
                                [center[0] - radius, center[1] + radius],
                                [center[0] + radius, center[1] + radius]
                            ])
                
                if len(all_points) < 4:
                    continue
                
                # Compute bounding dimensions
                xs = [p[0] for p in all_points if len(p) >= 2]
                ys = [p[1] for p in all_points if len(p) >= 2]
                
                if not xs or not ys:
                    continue
                
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                
                if width <= 0 or height <= 0:
                    continue
                
                aspect_ratio = max(width, height) / min(width, height)
                
                # Only elongated contours qualify
                if aspect_ratio < self.aspect_threshold:
                    continue

                # Skip root contours or very large contours occupying >80% area
                if any(eid in outer_contour_ids for eid in entity_ids):
                    continue
                if drawing_area > 0:
                    if (width * height) / drawing_area > 0.8:
                        continue
                
                counter += 1
                center_x = round((min(xs) + max(xs)) / 2, 4)
                center_y = round((min(ys) + max(ys)) / 2, 4)
                
                candidates.append({
                    "candidate_id": f"sc_{counter:05d}",
                    "entity_id": entity_ids,  # List of entity IDs forming the contour
                    "aspect_ratio": round(aspect_ratio, 4),
                    "width": round(width, 4),
                    "height": round(height, 4),
                    "center": [center_x, center_y],
                    "point_count": len(all_points),
                    "is_closed": True,
                    "source": "contour"
                })

        logger.info(
            f"SlotCandidateDetector: candidates={len(candidates)}"
        )

        return {
            "slot_candidates": candidates,
            "statistics": {
                "total_candidates": len(candidates),
                "polylines_analyzed": sum(
                    1 for e in entities
                    if e.get("entity_type") in ("LWPOLYLINE", "POLYLINE")
                ),
                "contours_analyzed": len(contours) if structural_result else 0
            },
        }
