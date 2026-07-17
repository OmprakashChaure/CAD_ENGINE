from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

from schemas.geometry_schema import (
    FilterResult,
    FilterStatistics,
    FilteredEntity,
)

logger = get_logger(__name__)


class DuplicateFilter:
    """
    Canonical geometry duplicate detector.

    Behavior:
      - First occurrence: KEPT as canonical instance
      - Exact duplicates: QUARANTINED (not removed)
      - Unsignatured entities: always KEPT (conservative)

    Signatures are built from entity["geometry"] ONLY.
    Rounding to 5 decimal places for deterministic matching.
    """

    def __init__(self):
        self.seen: Dict[Tuple, str] = {}

    def _build_signature(
        self,
        entity: Dict,
    ) -> Optional[Tuple]:
        """
        Build a deterministic geometry signature.
        Returns None for entity types without signature support
        (those entities are always preserved).
        """
        entity_type = entity["entity_type"]
        geometry = entity.get("geometry")

        if geometry is None:
            return None

        # -----------------------------------------
        # LINE
        # -----------------------------------------
        if entity_type == "LINE":
            start = tuple(
                round(v, 5) for v in geometry["start"]
            )
            end = tuple(
                round(v, 5) for v in geometry["end"]
            )
            # Sort endpoints for direction-independent matching
            return ("LINE", tuple(sorted([start, end])))

        # -----------------------------------------
        # CIRCLE
        # -----------------------------------------
        elif entity_type == "CIRCLE":
            center = tuple(
                round(v, 5) for v in geometry["center"]
            )
            radius = round(geometry["radius"], 5)
            return ("CIRCLE", center, radius)

        # -----------------------------------------
        # ARC
        # -----------------------------------------
        elif entity_type == "ARC":
            center = tuple(
                round(v, 5) for v in geometry["center"]
            )
            radius = round(geometry["radius"], 5)
            sa = round(geometry.get("start_angle", 0), 3)
            ea = round(geometry.get("end_angle", 0), 3)
            return ("ARC", center, radius, sa, ea)

        # -----------------------------------------
        # LWPOLYLINE / POLYLINE
        # -----------------------------------------
        elif entity_type in ("LWPOLYLINE", "POLYLINE"):
            points = geometry.get("points", [])
            if not points:
                return None
            # Build signature from rounded point sequence
            pts = tuple(
                tuple(round(v, 4) for v in pt)
                for pt in points
            )
            closed = geometry.get("closed", False)
            return (entity_type, pts, closed)

        return None

    def filter(
        self,
        entities: List[Dict],
    ) -> FilterResult:

        kept = []
        quarantined = []
        removed = []

        for entity in entities:

            try:
                signature = self._build_signature(entity)

                if signature is None:
                    # No signature support — always preserve
                    kept.append(entity)
                    continue

                if signature in self.seen:
                    # Exact duplicate — quarantine (NOT remove)
                    entity["possible_overlap"] = True
                    entity["overlap_confidence"] = 1.0

                    quarantined.append(
                        FilteredEntity(
                            entity=entity,
                            reason="exact_geometric_duplicate",
                        )
                    )

                    logger.debug(
                        f"Quarantined duplicate: "
                        f"{entity.get('entity_id')} "
                        f"(canonical: {self.seen[signature]})"
                    )
                else:
                    # First occurrence — canonical instance
                    self.seen[signature] = entity.get("entity_id", "unknown")
                    kept.append(entity)

            except Exception as exc:
                logger.warning(
                    f"DuplicateFilter failed "
                    f"for {entity.get('entity_id')}: {exc}"
                )
                # Conservative: keep on error
                kept.append(entity)

        stats = FilterStatistics(
            input_entities=len(entities),
            kept_entities=len(kept),
            quarantined_entities=len(quarantined),
            removed_entities=len(removed),
        )

        logger.info(
            f"DuplicateFilter: kept={len(kept)} "
            f"quarantined={len(quarantined)}"
        )

        return FilterResult(
            kept_entities=kept,
            quarantined_entities=quarantined,
            removed_entities=removed,
            statistics=stats,
        )
