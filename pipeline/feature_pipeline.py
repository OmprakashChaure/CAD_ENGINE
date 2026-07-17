"""
Feature Pipeline — orchestrate engineering feature candidate detection.

Stages:
  1. Hole candidate detection (concentric circular systems)
  2. Slot candidate detection (elongated closed contours)
  3. Radial pattern detection (repeated angular structures)
  4. Symmetry analysis (mirrored/repeated geometry)
  5. Feature-region grouping (associate candidates with regions)

Does NOT:
  - Assign semantic manufacturing labels
  - Infer engineering function
  - Generate AI-based classifications
  - Mutate upstream topology or geometry
"""
from typing import Any, Dict, List

from core.features.hole_candidate_detector import HoleCandidateDetector
from core.features.slot_candidate_detector import SlotCandidateDetector
from core.features.radial_pattern_detector import RadialPatternDetector
from core.features.symmetry_analyzer import SymmetryAnalyzer
from core.features.feature_region_grouper import FeatureRegionGrouper
from utils.logger import get_logger

logger = get_logger(__name__)


class FeaturePipeline:
    """
    Orchestrate deterministic feature candidate detection.

    Input: filtered entities + structural analysis result
    Output: feature candidates with region associations
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(
        self,
        entities: List[Dict],
        structural_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run full feature candidate detection pipeline.

        Args:
            entities: canonical entities (post-filtering)
            structural_result: output from StructuralPipeline

        Returns:
            {
                "hole_candidates": { ... },
                "slot_candidates": { ... },
                "radial_patterns": { ... },
                "symmetry": { ... },
                "feature_regions": { ... },
                "statistics": { ... }
            }
        """
        logger.info(
            f"FeaturePipeline: analyzing {len(entities)} entities"
        )

        concentric_result = structural_result.get("concentric_groups", {})
        region_result = structural_result.get("regions", {})
        regions = region_result.get("regions", [])

        # Stage 1: Hole candidate detection
        hole_detector = HoleCandidateDetector()
        hole_result = hole_detector.detect(entities, concentric_result)

        # Stage 2: Slot candidate detection
        slot_detector = SlotCandidateDetector(
            aspect_threshold=self.config.get("slot_aspect_threshold", 2.0)
        )
        slot_result = slot_detector.detect(entities, structural_result)

        # Stage 3: Radial pattern detection
        radial_detector = RadialPatternDetector(
            min_count=self.config.get("radial_min_count", 3),
        )
        radial_result = radial_detector.detect(
            hole_result["hole_candidates"]
        )

        # Stage 4: Symmetry analysis
        symmetry_analyzer = SymmetryAnalyzer(
            tolerance=self.config.get("symmetry_tolerance", 0.01)
        )
        symmetry_result = symmetry_analyzer.analyze(entities)

        # Stage 5: Feature-region grouping
        grouper = FeatureRegionGrouper()
        grouping_result = grouper.group(
            hole_candidates=hole_result["hole_candidates"],
            slot_candidates=slot_result["slot_candidates"],
            radial_patterns=radial_result["radial_patterns"],
            regions=regions,
            entities=entities,
        )

        # Combined statistics
        statistics = {
            "holes": hole_result["statistics"],
            "slots": slot_result["statistics"],
            "radial_patterns": radial_result["statistics"],
            "symmetry": symmetry_result["statistics"],
            "feature_regions": grouping_result["statistics"],
        }

        logger.info(
            f"FeaturePipeline complete: "
            f"holes={hole_result['statistics']['total_candidates']} "
            f"slots={slot_result['statistics']['total_candidates']} "
            f"radial={radial_result['statistics']['total_patterns']} "
            f"symmetry={symmetry_result['statistics']['total_groups']}"
        )

        return {
            "hole_candidates": hole_result,
            "slot_candidates": slot_result,
            "radial_patterns": radial_result,
            "symmetry": symmetry_result,
            "feature_regions": grouping_result,
            "statistics": statistics,
        }
