from pathlib import Path
from typing import List

from core.reader.dxf_loader import DXFLoader
from core.reader.entity_iterator import EntityIterator
from utils.logger import get_logger


logger = get_logger(__name__)


class ExtractionPipeline:
    """
    Phase-1B extraction pipeline.

    ONLY:
    - load DXF
    - iterate entities
    - normalize entities

    NO filtering or semantic logic yet.
    """

    def __init__(self, dxf_path: str):
        self.dxf_path = Path(dxf_path)

    def run(self):

        logger.info("Starting extraction pipeline")

        loader = DXFLoader(str(self.dxf_path))

        document = loader.load()

        iterator = EntityIterator(
            document=document,
            source_file=self.dxf_path.name,
        )

        entities = list(iterator.iterate())

        logger.info(
            f"Initial entities: {len(entities)}"
        )

        from core.filters.text_filter import TextFilter
        from core.filters.degenerate_filter import DegenerateFilter
        from core.filters.duplicate_filter import DuplicateFilter
        from core.filters.layer_filter import LayerFilter
        from core.filters.border_filter import BorderFilter

        filters = [
            TextFilter(),
            DegenerateFilter(),
            DuplicateFilter(),
            LayerFilter(),
            BorderFilter(),
        ]

        filter_reports = []
        quarantined_entities = []
        removed_entities = []

        for filter_stage in filters:

            result = filter_stage.filter(entities)

            # Preserve active entities
            entities = result.kept_entities

            # IMPORTANT:
            # quarantined entities are NOT deleted
            # they remain accessible downstream
            quarantined_entities.extend(result.quarantined_entities)
            removed_entities.extend(result.removed_entities)

            filter_reports.append({
                "filter": filter_stage.__class__.__name__,
                "statistics": result.statistics.model_dump(),
            })

        logger.info(
            f"Final filtered entities: {len(entities)}"
        )
        logger.info(
            f"Quarantined entities: "
            f"{len(quarantined_entities)}"
        )
        logger.info(
            f"Removed entities: "
            f"{len(removed_entities)}"
        )

        return {
            "entities": entities,
            # PLANNED, NOT YET ACTIVE: quarantine_store downstream consumer.
            # Quarantined entities are preserved here for future use by a
            # dedicated quarantine analysis stage (e.g. to recover DIMENSIONs
            # whose geometry was unsupported but whose text annotations contain
            # valid engineering data). Until that stage is implemented, this
            # list is carried through the pipeline but not read downstream.
            "quarantined_entities": [
                q.model_dump()
                for q in quarantined_entities
            ],
            "removed_entities": [
                r.model_dump()
                for r in removed_entities
            ],
            "filter_reports": filter_reports,
        }