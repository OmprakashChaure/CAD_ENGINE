"""
Refinement Pipeline — orchestrate feature candidate refinement.

Stages:
  1. Confidence analysis (structural reliability scoring)
  2. Hierarchy building (parent-child structural organization)
  3. Conflict detection (overlapping candidate claims)
  4. Repetition consolidation (repeated structural patterns)
  5. Ambiguity tracking (explicit uncertainty preservation)

Does NOT:
  - Assign semantic engineering labels
  - Infer manufacturing operations
  - Generate AI-based classifications
  - Force ambiguity resolution
  - Mutate upstream topology or geometry
"""
from typing import Any, Dict, List

from core.features.candidate_confidence_analyzer import CandidateConfidenceAnalyzer
from core.features.feature_hierarchy_builder import FeatureHierarchyBuilder
from core.features.candidate_conflict_resolver import CandidateConflictResolver
from core.features.repeated_pattern_consolidator import RepeatedPatternConsolidator
from core.features.structural_ambiguity_tracker import StructuralAmbiguityTracker
from utils.logger import get_logger

logger = get_logger(__name__)


class RefinementPipeline:
    """
    Orchestrate deterministic feature candidate refinement.

    Input: feature candidate result from FeaturePipeline
    Output: refined candidates with confidence, hierarchy, conflicts, ambiguity
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(
        self,
        feature_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run full refinement pipeline.

        Args:
            feature_result: output from FeaturePipeline

        Returns:
            {
                "confidence": { ... },
                "hierarchy": { ... },
                "conflicts": { ... },
                "repetitions": { ... },
                "ambiguity": { ... },
                "statistics": { ... }
            }
        """
        logger.info("RefinementPipeline: starting")

        # Stage 1: Confidence analysis
        confidence_analyzer = CandidateConfidenceAnalyzer()
        confidence_result = confidence_analyzer.analyze(feature_result)

        # Stage 2: Hierarchy building
        hierarchy_builder = FeatureHierarchyBuilder()
        hierarchy_result = hierarchy_builder.build(feature_result)

        # Stage 3: Conflict detection
        conflict_resolver = CandidateConflictResolver()
        conflict_result = conflict_resolver.detect(feature_result)

        # Stage 4: Repetition consolidation
        consolidator = RepeatedPatternConsolidator(
            precision=self.config.get("signature_precision", 3)
        )
        repetition_result = consolidator.consolidate(feature_result)

        # Stage 5: Ambiguity tracking
        ambiguity_tracker = StructuralAmbiguityTracker(
            threshold=self.config.get("ambiguity_threshold", 0.5)
        )
        ambiguity_result = ambiguity_tracker.track(
            confidence_result, conflict_result
        )

        # Combined statistics
        statistics = {
            "confidence": confidence_result["statistics"],
            "hierarchy": hierarchy_result["statistics"],
            "conflicts": conflict_result["statistics"],
            "repetitions": repetition_result["statistics"],
            "ambiguity": ambiguity_result["statistics"],
        }

        logger.info(
            f"RefinementPipeline complete: "
            f"scored={confidence_result['statistics']['total_scored']} "
            f"conflicts={conflict_result['statistics']['total_conflicts']} "
            f"repetitions={repetition_result['statistics']['total_repetition_groups']} "
            f"ambiguous={ambiguity_result['statistics']['total_ambiguous']}"
        )

        return {
            "confidence": confidence_result,
            "hierarchy": hierarchy_result,
            "conflicts": conflict_result,
            "repetitions": repetition_result,
            "ambiguity": ambiguity_result,
            "statistics": statistics,
        }
