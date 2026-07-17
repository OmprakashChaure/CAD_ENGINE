"""
Inference Conditioner — create masked training samples for dimension inference.

For each eligible target, produces an inference-conditioned sample where:
  - The target dimension value is HIDDEN (label)
  - Structural reasoning context is PRESERVED (input)
  - Direct answer leakage is PREVENTED

The model must learn to INFER the hidden value from:
  - Topology neighbors and their visible dimensions
  - Repetition group membership (same-dimension siblings)
  - Concentric hierarchy (radius relationships)
  - Feature candidate context
  - Structural region context

Does NOT:
  - Randomly mask (deterministic only)
  - Destroy reasoning substrate
  - Add embeddings or vectors
  - Inject probabilistic logic
"""
from typing import Any, Dict, List
import copy

from utils.logger import get_logger

logger = get_logger(__name__)


class InferenceConditioner:
    """
    Create inference-conditioned training samples.

    Each sample contains:
      - visible_context: what the model sees (geometry + structure, target masked)
      - hidden_label: what the model must predict (the masked dimension)
      - reasoning_evidence: preserved structural signals for inference
    """

    def condition(
        self,
        targets: List[Dict],
        context_packages: List[Dict],
    ) -> Dict[str, Any]:
        """
        Build inference-conditioned samples from targets + context.

        Returns:
            {
                "training_samples": [
                    {
                        "sample_id": "smp_00001",
                        "entity_id": str,
                        "entity_type": str,

                        "hidden_label": {
                            "dimension_type": str,
                            "target_value": float,
                        },

                        "visible_context": {
                            "entity_type": str,
                            "topology_neighbors": [...],
                            "neighbor_dimensions": [...],
                            "feature_membership": {...} | None,
                            "repetition_group": {...} | None,
                            "concentric_group": {...} | None,
                            "region_size": int,
                            "other_own_dimensions": [...],
                        },

                        "leakage_audit": {
                            "target_in_own_dims": bool,
                            "target_in_neighbor_dims": bool,
                            "leakage_prevented": bool,
                        },
                    }
                ],
                "statistics": { ... }
            }
        """
        logger.info(
            f"InferenceConditioner: conditioning "
            f"{len(targets)} targets"
        )

        # Index context packages by entity_id
        pkg_by_id: Dict[str, Dict] = {}
        for pkg in context_packages:
            pkg_by_id[pkg["entity_id"]] = pkg

        samples: List[Dict] = []
        counter = 0
        leakage_detected = 0

        for target in targets:
            if not target.get("eligible", False):
                continue

            entity_id = target["entity_id"]
            pkg = pkg_by_id.get(entity_id)
            if pkg is None:
                continue

            counter += 1

            target_dim_type = target["dimension_type"]
            target_value = target["target_value"]

            # Build visible context with target MASKED
            visible_ctx, leakage_audit = self._build_masked_context(
                pkg, target_dim_type, target_value
            )

            if not leakage_audit["leakage_prevented"]:
                leakage_detected += 1

            samples.append({
                "sample_id": f"smp_{counter:05d}",
                "entity_id": entity_id,
                "entity_type": target["entity_type"],

                "hidden_label": {
                    "dimension_type": target_dim_type,
                    "target_value": target_value,
                },

                "visible_context": visible_ctx,

                "leakage_audit": leakage_audit,
            })

        logger.info(
            f"InferenceConditioner: samples={len(samples)} "
            f"leakage_issues={leakage_detected}"
        )

        return {
            "training_samples": samples,
            "statistics": {
                "total_samples": len(samples),
                "leakage_issues": leakage_detected,
                "leakage_free": len(samples) - leakage_detected,
            },
        }

    def _build_masked_context(
        self,
        pkg: Dict,
        target_dim_type: str,
        target_value: float,
    ) -> tuple:
        """
        Build visible context with the target dimension masked out.

        Returns: (visible_context, leakage_audit)
        """
        # Other own dimensions (NOT the target)
        other_own = [
            d for d in pkg.get("own_dimensions", [])
            if not (
                d["dimension_type"] == target_dim_type and
                abs(d["value"] - target_value) < 1e-6
            )
        ]

        # Neighbor dimensions — filter out any that directly leak target
        # (neighbor with exact same value could be valid reasoning evidence
        # from repetition, so we KEEP it but FLAG it in audit)
        neighbor_dims = pkg.get("neighbor_dimensions", [])
        target_in_neighbors = any(
            abs(nd["value"] - target_value) < 1e-6
            for nd in neighbor_dims
        )

        # Check if target value still appears in own_dimensions
        target_in_own = any(
            d["dimension_type"] == target_dim_type and
            abs(d["value"] - target_value) < 1e-6
            for d in other_own
        )

        # Build visible context
        visible_context = {
            "entity_type": pkg["entity_type"],
            "topology_neighbors": pkg.get("topology_neighbors", []),
            "neighbor_dimensions": neighbor_dims,
            "feature_membership": pkg.get("feature_membership"),
            "repetition_group": pkg.get("repetition_group"),
            "concentric_group": pkg.get("concentric_group"),
            "contour_hierarchy": pkg.get("contour_hierarchy"),
            "region_size": pkg.get("region_size", 1),
            "other_own_dimensions": other_own,
        }

        # Leakage audit
        leakage_audit = {
            "target_in_own_dims": target_in_own,
            "target_in_neighbor_dims": target_in_neighbors,
            "leakage_prevented": not target_in_own,
        }

        return visible_context, leakage_audit
