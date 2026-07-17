"""
Context Pipeline — orchestrate engineering context organization.

Stages:
  1. Candidate relationship building (structural associations)
  2. Context cluster analysis (connected candidate groups)
  3. Relationship confidence scoring
  4. Structural dependency mapping
  5. Contextual ambiguity propagation

Does NOT:
  - Assign semantic engineering labels
  - Infer manufacturing operations
  - Generate AI-based classifications
  - Force ambiguity resolution
  - Mutate upstream topology or geometry
"""
from typing import Any, Dict, List

from core.features.candidate_relationship_builder import CandidateRelationshipBuilder
from core.features.context_cluster_analyzer import ContextClusterAnalyzer
from core.features.relationship_confidence_manager import RelationshipConfidenceManager
from core.features.structural_dependency_mapper import StructuralDependencyMapper
from core.features.contextual_ambiguity_propagator import ContextualAmbiguityPropagator
from utils.logger import get_logger

logger = get_logger(__name__)


class ContextPipeline:
    """
    Orchestrate deterministic engineering context organization.

    Input: feature result + refinement result
    Output: context-organized structural dataset
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(
        self,
        feature_result: Dict[str, Any],
        refinement_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run full context organization pipeline.

        Args:
            feature_result: output from FeaturePipeline
            refinement_result: output from RefinementPipeline

        Returns:
            {
                "relationships": { ... },
                "clusters": { ... },
                "relationship_confidence": { ... },
                "dependencies": { ... },
                "ambiguity_propagation": { ... },
                "statistics": { ... }
            }
        """
        logger.info("ContextPipeline: starting")

        # Stage 1: Build candidate relationships
        rel_builder = CandidateRelationshipBuilder()
        relationship_result = rel_builder.build(
            feature_result, refinement_result
        )

        # Collect all candidate IDs for clustering
        all_candidate_ids = self._collect_all_candidate_ids(feature_result)

        # Stage 2: Context cluster analysis
        cluster_analyzer = ContextClusterAnalyzer()
        cluster_result = cluster_analyzer.analyze(
            relationship_result["adjacency"],
            all_candidate_ids,
        )

        # Stage 3: Relationship confidence
        confidence_scores = refinement_result.get(
            "confidence", {}
        ).get("confidence_scores", [])

        conf_manager = RelationshipConfidenceManager()
        rel_confidence_result = conf_manager.evaluate(
            relationship_result["relationships"],
            confidence_scores,
        )

        # Stage 4: Structural dependency mapping
        hierarchy_result = refinement_result.get("hierarchy", {})
        dep_mapper = StructuralDependencyMapper()
        dependency_result = dep_mapper.map(feature_result, hierarchy_result)

        # Stage 5: Ambiguity propagation
        ambiguity_result = refinement_result.get("ambiguity", {})
        amb_propagator = ContextualAmbiguityPropagator()
        propagation_result = amb_propagator.propagate(
            rel_confidence_result["scored_relationships"],
            ambiguity_result,
            cluster_result["clusters"],
        )

        # Combined statistics
        statistics = {
            "relationships": relationship_result["statistics"],
            "clusters": cluster_result["statistics"],
            "relationship_confidence": rel_confidence_result["statistics"],
            "dependencies": dependency_result["statistics"],
            "ambiguity_propagation": propagation_result["statistics"],
        }

        logger.info(
            f"ContextPipeline complete: "
            f"relationships={relationship_result['statistics']['total_relationships']} "
            f"clusters={cluster_result['statistics']['total_clusters']} "
            f"dependencies={dependency_result['statistics']['total_dependencies']} "
            f"ambiguous_rels={propagation_result['statistics']['total_ambiguous_relationships']}"
        )

        return {
            "relationships": relationship_result,
            "clusters": cluster_result,
            "relationship_confidence": rel_confidence_result,
            "dependencies": dependency_result,
            "ambiguity_propagation": propagation_result,
            "statistics": statistics,
        }

    def _collect_all_candidate_ids(
        self, feature_result: Dict[str, Any]
    ) -> List[str]:
        """Collect all candidate IDs from feature result."""
        ids: List[str] = []

        for hc in feature_result.get("hole_candidates", {}).get("hole_candidates", []):
            ids.append(hc["candidate_id"])

        for sc in feature_result.get("slot_candidates", {}).get("slot_candidates", []):
            ids.append(sc["candidate_id"])

        for rp in feature_result.get("radial_patterns", {}).get("radial_patterns", []):
            ids.append(rp["pattern_id"])

        return sorted(set(ids))
