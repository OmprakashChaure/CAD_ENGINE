from typing import Dict, List, Optional

from utils.logger import get_logger

from schemas.geometry_schema import (
    FilterResult,
    FilterStatistics,
    FilteredEntity,
)

logger = get_logger(__name__)


class BorderFilter:
    """
    Detects likely drawing borders/frames using canonical geometry.

    Detection strategies:
      1. Long lines (length > threshold)
      2. Large closed polylines occupying extreme bounding area

    Behavior: TAG and QUARANTINE suspicious borders.
    Does NOT aggressively remove — preserves for future validation.
    """

    LARGE_LINE_THRESHOLD = 1000.0
    FRAME_AREA_RATIO = 0.85  # Polyline occupying >85% of drawing bbox

    def filter(
        self,
        entities: List[Dict],
    ) -> FilterResult:

        kept = []
        quarantined = []
        removed = []

        # Compute drawing bounding box from all entities
        drawing_bbox = self._compute_drawing_bbox(entities)

        for entity in entities:

            try:
                entity_type = entity["entity_type"]
                geometry = entity.get("geometry")

                if geometry is None:
                    kept.append(entity)
                    continue

                is_border = False
                confidence = 0.0

                # Strategy 1: Long lines
                if entity_type == "LINE":
                    length = geometry.get("length", 0.0)
                    if length > self.LARGE_LINE_THRESHOLD:
                        is_border = True
                        confidence = min(0.6 + (length / 5000.0) * 0.3, 0.95)

                # Strategy 2: Large closed polylines (page frames)
                elif entity_type in ("LWPOLYLINE", "POLYLINE"):
                    if geometry.get("closed", False) and drawing_bbox:
                        poly_bbox = self._polyline_bbox(geometry)
                        if poly_bbox:
                            ratio = self._area_ratio(poly_bbox, drawing_bbox)
                            if ratio > self.FRAME_AREA_RATIO:
                                # Genuine engineering geometry on layer 'GEOMETRY' or dimensioned contours are not page frames
                                if entity.get("layer", "").upper() == "GEOMETRY":
                                    is_border = False
                                elif self._is_dimensioned(poly_bbox, entities):
                                    is_border = False
                                else:
                                    is_border = True
                                    confidence = min(0.7 + ratio * 0.2, 0.95)

                if is_border:
                    entity["possible_border"] = True
                    entity["border_confidence"] = round(confidence, 3)
                    entity["topology_exclude"] = True

                    quarantined.append(
                        FilteredEntity(
                            entity=entity,
                            reason="suspected_border_frame",
                        )
                    )

                    logger.debug(
                        f"Border quarantined: "
                        f"{entity.get('entity_id')} "
                        f"conf={confidence:.2f}"
                    )
                else:
                    kept.append(entity)

            except Exception as exc:
                logger.warning(
                    f"BorderFilter failed "
                    f"for {entity.get('entity_id')}: {exc}"
                )
                kept.append(entity)

        stats = FilterStatistics(
            input_entities=len(entities),
            kept_entities=len(kept),
            quarantined_entities=len(quarantined),
            removed_entities=len(removed),
        )

        logger.info(
            f"BorderFilter: kept={len(kept)} "
            f"quarantined={len(quarantined)}"
        )

        # Diagnostic: report drawing bbox for topology verification
        if drawing_bbox and quarantined:
            draw_w = drawing_bbox["xmax"] - drawing_bbox["xmin"]
            draw_h = drawing_bbox["ymax"] - drawing_bbox["ymin"]
            logger.debug(
                f"BorderFilter drawing bbox: "
                f"{draw_w:.1f} x {draw_h:.1f} | "
                f"quarantined {len(quarantined)} frame candidates"
            )

        return FilterResult(
            kept_entities=kept,
            quarantined_entities=quarantined,
            removed_entities=removed,
            statistics=stats,
        )

    def _compute_drawing_bbox(
        self, entities: List[Dict]
    ) -> Optional[Dict]:
        """Compute overall drawing bounding box from all geometry."""
        xs, ys = [], []

        for e in entities:
            geom = e.get("geometry")
            if geom is None:
                continue

            etype = e["entity_type"]

            if etype == "LINE":
                for pt in [geom.get("start"), geom.get("end")]:
                    if pt:
                        xs.append(pt[0])
                        ys.append(pt[1])
            elif etype == "CIRCLE":
                c = geom.get("center")
                r = geom.get("radius", 0)
                if c:
                    xs.extend([c[0] - r, c[0] + r])
                    ys.extend([c[1] - r, c[1] + r])
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                for pt in geom.get("points", []):
                    xs.append(pt[0])
                    ys.append(pt[1])
            elif etype == "ARC":
                c = geom.get("center")
                r = geom.get("radius", 0)
                if c:
                    xs.extend([c[0] - r, c[0] + r])
                    ys.extend([c[1] - r, c[1] + r])

        if not xs or not ys:
            return None

        return {
            "xmin": min(xs), "xmax": max(xs),
            "ymin": min(ys), "ymax": max(ys),
        }

    def _polyline_bbox(self, geometry: Dict) -> Optional[Dict]:
        """Compute bounding box of a polyline from its points."""
        points = geometry.get("points", [])
        if len(points) < 3:
            return None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return {
            "xmin": min(xs), "xmax": max(xs),
            "ymin": min(ys), "ymax": max(ys),
        }

    def _area_ratio(
        self, poly_bbox: Dict, drawing_bbox: Dict
    ) -> float:
        """Ratio of polyline area to drawing area."""
        poly_area = (
            (poly_bbox["xmax"] - poly_bbox["xmin"]) *
            (poly_bbox["ymax"] - poly_bbox["ymin"])
        )
        draw_area = (
            (drawing_bbox["xmax"] - drawing_bbox["xmin"]) *
            (drawing_bbox["ymax"] - drawing_bbox["ymin"])
        )
        if draw_area <= 0:
            return 0.0
        return poly_area / draw_area

    def _is_dimensioned(self, bbox: Dict, entities: List[Dict]) -> bool:
        """Check if the bounding box dimensions match any dimension callouts in the drawing."""
        w = round(bbox["xmax"] - bbox["xmin"], 4)
        h = round(bbox["ymax"] - bbox["ymin"], 4)
        
        import re
        for e in entities:
            if e.get("entity_type") not in ("DIMENSION", "MTEXT", "TEXT"):
                continue
            geom = e.get("geometry", {})
            text = geom.get("text", "")
            if not text:
                continue
            
            # Extract numbers from text
            nums = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", text)]
            for num in nums:
                # If a dimension number matches width or height within 1% tolerance
                if (w > 0 and abs(num - w) / w < 0.01) or (h > 0 and abs(num - h) / h < 0.01):
                    return True
        return False
