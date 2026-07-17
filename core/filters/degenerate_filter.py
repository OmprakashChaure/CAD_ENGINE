from typing import Dict, List
from collections import Counter

from utils.logger import get_logger

from schemas.geometry_schema import (
    FilterResult,
    FilterStatistics,
    FilteredEntity,
)

logger = get_logger(__name__)

EPSILON = 1e-6


class DegenerateFilter:
    """
    Canonical geometry validation filter.

    Validates normalized geometry dictionaries.
    Distinguishes between:
      - unsupported entities (geometry=None, supported=False) → quarantine
      - corrupted geometry (geometry=None on supported type) → remove
      - degenerate geometry (tiny/invalid) → quarantine
      - valid geometry → keep

    Conservative: quarantine over remove when possible.
    """

    def filter(
        self,
        entities: List[Dict],
    ) -> FilterResult:

        kept = []
        quarantined = []
        removed = []

        # Diagnostic counters
        type_counts: Counter = Counter()
        validation_outcomes: Counter = Counter()

        for entity in entities:

            try:

                entity_type = entity["entity_type"]
                type_counts[entity_type] += 1

                geometry = entity.get("geometry")
                supported = entity.get("supported", True)

                # -----------------------------------------
                # UNSUPPORTED ENTITY TYPE
                # Geometry normalizer could not process this.
                # Quarantine (not remove) — may have future
                # annotation/dimension value.
                # -----------------------------------------

                if geometry is None and not supported:

                    quarantined.append(
                        FilteredEntity(
                            entity=entity,
                            reason=f"unsupported_geometry_type:{entity_type}",
                        )
                    )
                    validation_outcomes["unsupported"] += 1
                    continue

                # -----------------------------------------
                # CORRUPTED GEOMETRY
                # Supported type but geometry is None.
                # This should not happen — remove.
                # -----------------------------------------

                if geometry is None and supported:

                    removed.append(
                        FilteredEntity(
                            entity=entity,
                            reason="corrupted_geometry_null",
                        )
                    )
                    validation_outcomes["corrupted"] += 1
                    continue

                # -----------------------------------------
                # LINE VALIDATION
                # -----------------------------------------

                if entity_type == "LINE":

                    length = geometry.get("length", 0.0)

                    if length < 0:
                        removed.append(
                            FilteredEntity(
                                entity=entity,
                                reason="negative_length",
                            )
                        )
                        validation_outcomes["invalid"] += 1
                        continue

                    if length <= EPSILON:
                        quarantined.append(
                            FilteredEntity(
                                entity=entity,
                                reason="tiny_line",
                            )
                        )
                        validation_outcomes["tiny"] += 1
                        continue

                # -----------------------------------------
                # CIRCLE VALIDATION
                # -----------------------------------------

                elif entity_type == "CIRCLE":

                    radius = geometry.get("radius", 0.0)

                    if radius < 0:
                        removed.append(
                            FilteredEntity(
                                entity=entity,
                                reason="negative_radius",
                            )
                        )
                        validation_outcomes["invalid"] += 1
                        continue

                    if radius <= EPSILON:
                        quarantined.append(
                            FilteredEntity(
                                entity=entity,
                                reason="tiny_circle",
                            )
                        )
                        validation_outcomes["tiny"] += 1
                        continue

                # -----------------------------------------
                # ARC VALIDATION
                # -----------------------------------------

                elif entity_type == "ARC":

                    radius = geometry.get("radius", 0.0)

                    if radius <= EPSILON:
                        quarantined.append(
                            FilteredEntity(
                                entity=entity,
                                reason="tiny_arc",
                            )
                        )
                        validation_outcomes["tiny"] += 1
                        continue

                # -----------------------------------------
                # POLYLINE VALIDATION
                # -----------------------------------------

                elif entity_type in {"LWPOLYLINE", "POLYLINE"}:

                    points = geometry.get("points", [])

                    if len(points) < 2:
                        quarantined.append(
                            FilteredEntity(
                                entity=entity,
                                reason="invalid_polyline_too_few_points",
                            )
                        )
                        validation_outcomes["invalid"] += 1
                        continue

                # -----------------------------------------
                # PASSED VALIDATION
                # -----------------------------------------

                kept.append(entity)
                validation_outcomes["valid"] += 1

            except Exception as exc:

                removed.append(
                    FilteredEntity(
                        entity=entity,
                        reason=f"geometry_validation_error: {exc}",
                    )
                )
                validation_outcomes["error"] += 1

                logger.warning(
                    f"Degenerate validation failed "
                    f"for {entity.get('entity_id')}: {exc}"
                )

        stats = FilterStatistics(
            input_entities=len(entities),
            kept_entities=len(kept),
            quarantined_entities=len(quarantined),
            removed_entities=len(removed),
        )

        # Structured diagnostic logging
        logger.info(
            f"DegenerateFilter: kept={len(kept)} "
            f"quarantined={len(quarantined)} "
            f"removed={len(removed)}"
        )

        logger.debug(
            f"DegenerateFilter type distribution: "
            f"{dict(type_counts)}"
        )

        logger.debug(
            f"DegenerateFilter outcomes: "
            f"{dict(validation_outcomes)}"
        )

        return FilterResult(
            kept_entities=kept,
            quarantined_entities=quarantined,
            removed_entities=removed,
            statistics=stats,
        )
