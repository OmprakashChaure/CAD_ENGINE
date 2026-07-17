from typing import Dict, List

import yaml

from utils.logger import get_logger

from schemas.geometry_schema import (
    FilterResult,
    FilterStatistics,
    FilteredEntity,
)


logger = get_logger(__name__)


class LayerFilter:
    """
    Configurable layer filtering.
    """

    def __init__(
        self,
        config_path="configs/layer_rules.yaml"
    ):

        with open(config_path, "r") as fp:
            self.config = yaml.safe_load(fp)

        self.ignore_layers = {
            layer.upper()
            for layer in self.config["ignore_layers"]
        }

    def filter(self, entities: List[Dict]) -> FilterResult:

        kept = []
        quarantined = []
        removed = []

        for entity in entities:

            layer = entity["layer"].upper()

            if layer in self.ignore_layers:

                removed.append(
                    FilteredEntity(
                        entity=entity,
                        reason="ignored_layer",
                    )
                )

                continue

            kept.append(entity)

        stats = FilterStatistics(
            input_entities=len(entities),
            kept_entities=len(kept),
            quarantined_entities=len(quarantined),
            removed_entities=len(removed),
        )

        logger.info(
            f"LayerFilter removed {len(removed)} entities"
        )

        return FilterResult(
            kept_entities=kept,
            quarantined_entities=quarantined,
            removed_entities=removed,
            statistics=stats,
        )