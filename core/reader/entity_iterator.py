from typing import Dict, Generator

from utils.logger import get_logger
from utils.dxf_utils import (
    normalize_entity_type,
    normalize_layer,
)
from core.classifiers.geometry_normalizer import (
    GeometryNormalizer,
)

logger = get_logger(__name__)


SUPPORTED_TYPES = {
    "LINE",
    "CIRCLE",
    "ARC",
    "LWPOLYLINE",
    "POLYLINE",
    "SPLINE",
    "TEXT",
    "MTEXT",
    # PLANNED, NOT YET ACTIVE: INSERT block explode.
    # Currently INSERT entities pass through to quarantine (unsupported_geometry_type).
    # A future BlockExploder stage will expand INSERT sub-entities inline into the
    # modelspace entity stream, allowing title block, revision table and standard
    # symbol blocks to be resolved. Until that stage is implemented, INSERT is kept
    # in SUPPORTED_TYPES so it reaches the quarantine audit trail.
    "INSERT",
    "DIMENSION",
    "HATCH",
}


class EntityIterator:
    """
    Iterate DXF entities safely.
    """

    def __init__(self, document, source_file: str):
        self.document = document
        self.source_file = source_file

    def iterate(self) -> Generator[Dict, None, None]:
        """
        Yield normalized DXF entities.
        """

        modelspace = self.document.modelspace()

        counter = 0

        for entity in modelspace:

            counter += 1

            entity_type = normalize_entity_type(entity)

            if entity_type not in SUPPORTED_TYPES:
                logger.debug(
                    f"Skipping unsupported entity: {entity_type}"
                )
                continue

            # ---------------------------------------------------------
            # NORMALIZED GEOMETRY
            # ---------------------------------------------------------

            normalized = GeometryNormalizer.normalize(entity)

            # ---------------------------------------------------------
            # ANNOTATION ROUTING VISIBILITY
            # Entities without geometry support (TEXT, MTEXT,
            # DIMENSION, SPLINE, INSERT, HATCH) still enter
            # the pipeline for future annotation extraction.
            # They will be quarantined by DegenerateFilter as
            # "unsupported_geometry_type" — NOT silently dropped.
            # ---------------------------------------------------------

            if not normalized["supported"]:
                logger.debug(
                    f"Annotation-path entity: "
                    f"{entity_type} (handle={entity.dxf.handle}) "
                    f"→ will be quarantined downstream"
                )

            entity_data = {
                # -----------------------------------------------------
                # Stable entity identity
                # -----------------------------------------------------
                "entity_id": f"ent_{counter:05d}",

                # -----------------------------------------------------
                # Source metadata
                # -----------------------------------------------------
                "source_file": self.source_file,
                "entity_type": entity_type,
                "handle": entity.dxf.handle,
                "layer": normalize_layer(entity.dxf.layer),
                "linetype": getattr(entity.dxf, "linetype", None),
                "color": getattr(entity.dxf, "color", None),

                # -----------------------------------------------------
                # Canonical geometry
                # -----------------------------------------------------
                "geometry": normalized["geometry"],
                "supported": normalized["supported"],

                # -----------------------------------------------------
                # Confidence metadata
                # -----------------------------------------------------
                "possible_overlap": False,
                "overlap_confidence": 0.0,
            }

            yield entity_data