"""
Structural Pipeline — orchestrate structural engineering recognition.

Stages:
  1. Contour extraction (topology-derived chains)
  2. Loop detection (verified topological cycles)
  3. Concentric grouping (shared-center geometry)
  4. Region analysis (disconnected topology islands)

Does NOT:
  - Perform semantic inference
  - Generate manufacturing reasoning
  - Create AI-generated classifications
  - Mutate upstream topology or geometry
"""
from typing import Any, Dict, List

from core.grouping.contour_extractor import ContourExtractor
from core.grouping.loop_detector import LoopDetector
from core.grouping.concentric_grouping import ConcentricGrouping
from core.grouping.region_analyzer import RegionAnalyzer
from core.grouping.contour_hierarchy import ContourHierarchy
from utils.logger import get_logger

logger = get_logger(__name__)


class StructuralPipeline:
    """
    Orchestrate structural engineering recognition from topology.

    Input: filtered entities + topology result
    Output: structural analysis (contours, loops, concentric groups, regions)
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run full structural analysis pipeline.

        Args:
            entities: canonical entities (post-filtering)
            topology_result: output from TopologyPipeline

        Returns:
            {
                "contours": { ... },
                "loops": { ... },
                "concentric_groups": { ... },
                "regions": { ... },
                "statistics": { ... }
            }
        """
        logger.info(
            f"StructuralPipeline: analyzing {len(entities)} entities"
        )

        adjacency_list = topology_result.get("adjacency_list", {})

        # Stage 1: Contour extraction
        contour_extractor = ContourExtractor()
        contour_result = contour_extractor.extract(entities, topology_result)

        # Stage 2: Loop detection
        loop_detector = LoopDetector()
        loop_result = loop_detector.detect(
            contour_result["contours"],
            adjacency_list,
        )

        # Stage 3: Concentric grouping
        concentric = ConcentricGrouping(
            precision=self.config.get("center_precision", 4)
        )
        concentric_result = concentric.detect(entities)

        # Stage 4: Region analysis
        region_analyzer = RegionAnalyzer()
        region_result = region_analyzer.analyze(entities, adjacency_list)

        # Stage 5: Contour hierarchy (containment analysis)
        hierarchy_analyzer = ContourHierarchy()
        hierarchy_result = hierarchy_analyzer.analyze(entities)

        # Combined statistics
        statistics = {
            "contours": contour_result["statistics"],
            "loops": loop_result["statistics"],
            "concentric": concentric_result["statistics"],
            "regions": region_result["statistics"],
            "hierarchy": hierarchy_result["statistics"],
        }

        logger.info(
            f"StructuralPipeline complete: "
            f"contours={contour_result['statistics']['total_contours']} "
            f"loops={loop_result['statistics']['total_loops']} "
            f"concentric={concentric_result['statistics']['total_groups']} "
            f"regions={region_result['statistics']['total_regions']} "
            f"hierarchy_outer={hierarchy_result['statistics']['outer']}"
        )

        return {
            "contours": contour_result,
            "loops": loop_result,
            "concentric_groups": concentric_result,
            "regions": region_result,
            "contour_hierarchy": hierarchy_result,
            "statistics": statistics,
        }
