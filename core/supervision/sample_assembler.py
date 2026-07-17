"""
Sample Assembler — finalize training samples into export-ready format.

Assembles inference-conditioned samples into the final trainable structure:
  - input: visible reasoning context (what the model sees)
  - output: hidden dimension target (what the model predicts)
  - metadata: provenance, eligibility, structural justification

Does NOT:
  - Redesign architecture
  - Reinterpret geometry
  - Regenerate targets
  - Remask supervision
  - Add embeddings or vectors

Simply: assembles already-correct structures into final form.
"""
from typing import Any, Dict, List
from collections import Counter

from utils.logger import get_logger

logger = get_logger(__name__)


class SampleAssembler:
    """
    Assemble final trainable inference samples.

    Each sample represents one engineering inference problem:
      input → visible structural context
      output → hidden dimension value to predict
      meta → provenance and quality indicators
    """

    def assemble(
        self,
        training_samples: List[Dict],
        drawing_id: str,
    ) -> Dict[str, Any]:
        """
        Assemble final training dataset from conditioned samples.

        Args:
            training_samples: from InferenceConditioner
            drawing_id: source DXF identifier

        Returns:
            {
                "drawing_id": str,
                "final_samples": [
                    {
                        "sample_id": str,
                        "drawing_id": str,

                        "input": {
                            "entity_type": str,
                            "topology_neighbors": [...],
                            "neighbor_dimensions": [...],
                            "feature_context": {...} | None,
                            "repetition_context": {...} | None,
                            "concentric_context": {...} | None,
                            "other_dimensions": [...],
                            "region_size": int,
                        },

                        "output": {
                            "dimension_type": str,
                            "value": float,
                        },

                        "meta": {
                            "entity_id": str,
                            "leakage_free": bool,
                            "has_topology_evidence": bool,
                            "has_repetition_evidence": bool,
                            "has_concentric_evidence": bool,
                            "has_feature_evidence": bool,
                            "reasoning_signal_count": int,
                        },
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"SampleAssembler: assembling {len(training_samples)} "
            f"samples for {drawing_id}"
        )

        final_samples: List[Dict] = []

        for sample in training_samples:
            ctx = sample.get("visible_context", {})
            label = sample.get("hidden_label", {})
            audit = sample.get("leakage_audit", {})

            # Count reasoning signals available
            has_topo = len(ctx.get("topology_neighbors", [])) > 0
            has_rep = ctx.get("repetition_group") is not None
            has_conc = ctx.get("concentric_group") is not None
            has_feat = ctx.get("feature_membership") is not None
            has_hier = ctx.get("contour_hierarchy") is not None
            signal_count = sum([has_topo, has_rep, has_conc, has_feat, has_hier])

            # Signal strength classification (deterministic)
            if signal_count >= 3:
                signal_strength = "strong"
            elif signal_count >= 1:
                signal_strength = "medium"
            else:
                signal_strength = "weak"

            final_samples.append({
                "sample_id": sample["sample_id"],
                "drawing_id": drawing_id,

                "input": {
                    "entity_type": ctx.get("entity_type"),
                    "topology_neighbors": ctx.get("topology_neighbors", []),
                    "neighbor_dimensions": ctx.get("neighbor_dimensions", []),
                    "feature_context": ctx.get("feature_membership"),
                    "repetition_context": ctx.get("repetition_group"),
                    "concentric_context": ctx.get("concentric_group"),
                    "contour_hierarchy": ctx.get("contour_hierarchy"),
                    "other_dimensions": ctx.get("other_own_dimensions", []),
                    "region_size": ctx.get("region_size", 1),
                },

                "output": {
                    "dimension_type": label.get("dimension_type"),
                    "value": label.get("target_value"),
                },

                "meta": {
                    "entity_id": sample.get("entity_id"),
                    "leakage_free": audit.get("leakage_prevented", True),
                    "has_topology_evidence": has_topo,
                    "has_repetition_evidence": has_rep,
                    "has_concentric_evidence": has_conc,
                    "has_feature_evidence": has_feat,
                    "has_hierarchy_evidence": has_hier,
                    "reasoning_signal_count": signal_count,
                    "signal_strength": signal_strength,
                },
            })

        # Statistics
        total = len(final_samples)
        with_topo = sum(1 for s in final_samples if s["meta"]["has_topology_evidence"])
        with_rep = sum(1 for s in final_samples if s["meta"]["has_repetition_evidence"])
        with_conc = sum(1 for s in final_samples if s["meta"]["has_concentric_evidence"])
        with_feat = sum(1 for s in final_samples if s["meta"]["has_feature_evidence"])
        with_hier = sum(1 for s in final_samples if s["meta"]["has_hierarchy_evidence"])
        leakage_free = sum(1 for s in final_samples if s["meta"]["leakage_free"])

        signal_dist = {}
        strength_dist = Counter()
        for s in final_samples:
            sc = s["meta"]["reasoning_signal_count"]
            signal_dist[sc] = signal_dist.get(sc, 0) + 1
            strength_dist[s["meta"]["signal_strength"]] += 1

        logger.info(
            f"SampleAssembler: final={total} "
            f"leakage_free={leakage_free} "
            f"with_evidence={sum(1 for s in final_samples if s['meta']['reasoning_signal_count'] > 0)}"
        )

        return {
            "drawing_id": drawing_id,
            "final_samples": final_samples,
            "statistics": {
                "total_samples": total,
                "leakage_free": leakage_free,
                "with_topology_evidence": with_topo,
                "with_repetition_evidence": with_rep,
                "with_concentric_evidence": with_conc,
                "with_feature_evidence": with_feat,
                "with_hierarchy_evidence": with_hier,
                "signal_distribution": signal_dist,
                "signal_strength": dict(strength_dist),
            },
        }
