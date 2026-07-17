# SECTION 07 — PHASE 7: SUPERVISED DATASET GENERATION
# CAD_ENGINE Design Authority Document

---

## 7.1 PURPOSE

Phase 7 is the most complex phase. It transforms the geometric and structural
analysis from Phases 1-6 into supervised training samples for dimension inference.

Each training sample represents: "Given this visible geometric context, predict this hidden dimension."

**Orchestrator:** `pipeline/dataset_pipeline.py` → `DatasetPipeline.run()`
**Called from:** `main.py` line 224-233
**Inputs:** ALL previous phase outputs

---

## 7.2 DATASET PIPELINE INTERNAL STAGES

The DatasetPipeline.run() method executes 6 sequential stages (line 103-147):

```
Stage 1: SupervisionMapper    — DIMENSION/TEXT → geometry association
Stage 2: ContextPackager      — per-entity reasoning context assembly
Stage 3: TargetConstructor    — eligible target dimension extraction
Stage 4: InferenceConditioner — target masking + leakage audit
Stage 5: SampleAssembler      — final training sample construction
Stage 6: _assemble_context    — summary statistics for training context
```

---

## 7.3 STAGE 1: SUPERVISION MAPPER

**File:** `core/supervision/supervision_mapper.py`
**Class:** `SupervisionMapper`
**Tolerance:** `association_tolerance = 1.0` drawing units (line 105)

### Entity Separation (line 73-87)

```python
for entity in entities:
    if entity_type == "DIMENSION":
        supervision_ents.append(entity)
    elif entity_type in ("TEXT", "MTEXT"):
        if geometry.get("numeric_value") is not None:
            supervision_ents.append(entity)
    else:
        geometry_ents.append(entity)
```

TEXT/MTEXT entities are supervision only if they have a `numeric_value`
(established by GeometryNormalizer._normalize_text() classification).

### Computable Dimensions (line 123-196)

For every geometry entity, computes ALL measurable dimensions analytically:

| Entity Type | Dimensions Computed | Derivation String |
|------------|---------------------|-------------------|
| LINE | `length` | `"line_endpoint_distance"` |
| CIRCLE | `radius`, `diameter` | `"circle_radius"`, `"circle_diameter"` |
| ARC | `radius` | `"arc_radius"` |
| LWPOLYLINE | `width`, `height` | `"polyline_bounding_width"`, `"polyline_bounding_height"` |
| POLYLINE | `width`, `height` | `"polyline_bounding_width"`, `"polyline_bounding_height"` |

For LWPOLYLINE/POLYLINE bounding: `width = max(xs) - min(xs)`, `height = max(ys) - min(ys)`.

### Association Strategies (line 225-248)

**Strategy 1 — Target Point Proximity:**
```python
for tp in target_points:
    for entity in geometry_ents:
        ref_points = self._get_reference_points(etype, geom)
        for rp in ref_points:
            dist = sqrt((tp[0]-rp[0])^2 + (tp[1]-rp[1])^2)
            if dist < tolerance and dist < best_dist:
                best_entity = entity_id
```
Reference points per entity type:
- LINE → `start`, `end`
- CIRCLE/ARC → `center`
- LWPOLYLINE/POLYLINE → first 4 `points`

**Strategy 2 — Value Matching Fallback** (used only when Strategy 1 fails):
```python
ratio = abs(sup_value - comp_value) / comp_value
if ratio < 0.01: return comp["entity_id"]
```
Tolerance: 1% relative difference.

### Output

```python
{
    "supervision_entities": [...],
    "geometry_entities_count": int,
    "computable_dimensions": [{entity_id, dimension_type, value, derivation}],
    "supervision_mappings": [{supervision_entity_id, geometry_entity_id, supervision_value, mapping_method}],
    "unmapped_supervision": [{supervision_entity_id, supervision_value, reason}],
    "statistics": {
        "total_supervision_entities": int,
        "total_geometry_entities": int,
        "total_computable_dimensions": int,
        "total_mapped": int,
        "total_unmapped": int
    }
}
```

---

## 7.4 STAGE 2: CONTEXT PACKAGER

**File:** `core/supervision/context_packager.py`
**Class:** `ContextPackager`

### Purpose

For every geometry entity, assembles all structural evidence that would help
a model infer its dimensions. One context package per entity.

### Package Structure

```python
{
    "entity_id": str,
    "entity_type": str,
    "own_dimensions": [{dimension_type, value}],
    "topology_neighbors": [entity_id, ...],     # from adjacency_list
    "neighbor_dimensions": [                     # dimensions of neighbors
        {"neighbor_id": str, "dimension_type": str, "value": float}
    ],
    "feature_membership": {
        "candidate_id": str,
        "candidate_type": str,
        "radius_count": int | "aspect_ratio": float
    } | None,
    "repetition_group": {
        "group_id": str,
        "repetition_count": int,
        "signature": str
    } | None,
    "concentric_group": {
        "group_id": str,
        "radii": [...],
        "count": int
    } | None,
    "contour_hierarchy": {
        "contour_role": str,
        "nesting_depth": int,
        "child_count": int,
        "has_parent": bool
    } | None,
    "region_size": int
}
```

### Neighbor Cap (line 100)

```python
for nid in neighbors[:6]:   # Cap at 6 to prevent explosion
```

Neighbor dimensions are computed for first 6 topology neighbors only.

### Lookup Indices Built by ContextPackager

| Method | Input | Output |
|--------|-------|--------|
| `_index_dimensions()` | `computable_dimensions` | `{entity_id: [{dim_type, value}]}` |
| `_index_feature_membership()` | `feature_result` | `{entity_id: {candidate_info}}` |
| `_index_repetition_membership()` | `refinement_result`, `feature_result` | `{entity_id: {group_info}}` |
| `_index_concentric_membership()` | `structural_result` | `{entity_id: {group_info}}` |
| `_index_region_sizes()` | `structural_result` | `{entity_id: int}` |
| `_index_hierarchy()` | `structural_result` | `{entity_id: {hierarchy_info}}` |

**DIMENSION, TEXT, MTEXT entities are EXCLUDED from packaging (line 86-88):**
```python
if etype in ("DIMENSION", "TEXT", "MTEXT"):
    continue
```
These entities are supervision targets, not context inputs.

---

## 7.5 STAGE 3: TARGET CONSTRUCTOR

**File:** `core/supervision/target_constructor.py`
**Class:** `TargetConstructor`
**Min target value:** `MIN_TARGET_VALUE = 0.1` (line 27)

### Eligibility Criteria (line 137-184)

A dimension is eligible if ANY of these conditions is true:
1. Entity has topology neighbors (`has_topo`) → `"topology_connected"`
2. Entity has feature membership (`has_feature`) → `"feature_candidate_member"`
3. Entity has repetition group (`has_repetition`) → `"repetition_constrained"`
4. Entity has concentric group (`has_concentric`) → `"concentric_hierarchy"`
5. Region size > 1 (`region_size > 1`) → `"multi_entity_region"`
6. Circular geometry (diameter/radius) → `"measurable_circular_geometry"` (even if isolated)
7. Linear geometry > 1.0 (length/width/height) → `"measurable_linear_geometry"` / `"measurable_contour_geometry"`
8. Ineligible if none of the above → `"insufficient_structural_context"`

Additionally: `value < MIN_TARGET_VALUE (0.1)` → always ineligible.

### Target Dictionary

```python
{
    "target_id": "tgt_00001",
    "entity_id": str,
    "entity_type": str,
    "dimension_type": str,
    "target_value": float,
    "derivation": str,
    "structural_justification": str,
    "has_repetition_constraint": bool,
    "has_concentric_constraint": bool,
    "has_topology_context": bool,
    "eligible": bool
}
```

---

## 7.6 STAGE 4: INFERENCE CONDITIONER

**File:** `core/supervision/inference_conditioner.py`
**Class:** `InferenceConditioner`

### Core Operation: Target Masking

For each eligible target, creates a training sample where:
- The target dimension value is HIDDEN (placed in `hidden_label`)
- All OTHER own dimensions are VISIBLE in context
- Neighbor dimensions are VISIBLE
- Feature/repetition/concentric context is VISIBLE

### Masking Logic (line 159-165)

```python
other_own = [
    d for d in pkg.get("own_dimensions", [])
    if not (
        d["dimension_type"] == target_dim_type and
        abs(d["value"] - target_value) < 1e-6
    )
]
```

Exact value match with float tolerance `1e-6`.

### Leakage Audit (line 196-201)

```python
leakage_audit = {
    "target_in_own_dims": target_in_own,
    "target_in_neighbor_dims": target_in_neighbors,
    "leakage_prevented": not target_in_own,
}
```

**CRITICAL:** `leakage_prevented = not target_in_own` — the audit ONLY fails
if the target value STILL APPEARS in `other_own` after masking (which should
never happen if masking is correct). Neighbor dimensions with matching values
are flagged via `target_in_neighbor_dims` but do NOT cause leakage failure —
they represent valid repetition-based reasoning evidence.

### Training Sample Structure

```python
{
    "sample_id": "smp_00001",
    "entity_id": str,
    "entity_type": str,
    "hidden_label": {
        "dimension_type": str,
        "target_value": float
    },
    "visible_context": {
        "entity_type": str,
        "topology_neighbors": [...],
        "neighbor_dimensions": [...],
        "feature_membership": {...} | None,
        "repetition_group": {...} | None,
        "concentric_group": {...} | None,
        "contour_hierarchy": {...} | None,
        "region_size": int,
        "other_own_dimensions": [...]
    },
    "leakage_audit": {
        "target_in_own_dims": bool,
        "target_in_neighbor_dims": bool,
        "leakage_prevented": bool
    }
}
```

---

## 7.7 STAGE 5: SAMPLE ASSEMBLER

**File:** `core/supervision/sample_assembler.py`
**Class:** `SampleAssembler`

### Reasoning Signal Counting (line 99-104)

```python
has_topo  = len(ctx.get("topology_neighbors", [])) > 0
has_rep   = ctx.get("repetition_group") is not None
has_conc  = ctx.get("concentric_group") is not None
has_feat  = ctx.get("feature_membership") is not None
has_hier  = ctx.get("contour_hierarchy") is not None
signal_count = sum([has_topo, has_rep, has_conc, has_feat, has_hier])
```

### Signal Strength Classification (line 107-112)

```python
if signal_count >= 3: signal_strength = "strong"
elif signal_count >= 1: signal_strength = "medium"
else: signal_strength = "weak"
```

### Final Sample Structure

```python
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
        "contour_hierarchy": {...} | None,
        "other_dimensions": [...],
        "region_size": int
    },
    "output": {
        "dimension_type": str,
        "value": float
    },
    "meta": {
        "entity_id": str,
        "leakage_free": bool,
        "has_topology_evidence": bool,
        "has_repetition_evidence": bool,
        "has_concentric_evidence": bool,
        "has_feature_evidence": bool,
        "has_hierarchy_evidence": bool,
        "reasoning_signal_count": int,
        "signal_strength": "strong" | "medium" | "weak"
    }
}
```

---

## 7.8 PHASE 7 COMPLETE OUTPUT CONTRACT

```python
{
    "final_dataset": {
        "drawing_id": str,
        "final_samples": [...],
        "statistics": {
            "total_samples": int,
            "leakage_free": int,
            "with_topology_evidence": int,
            "with_repetition_evidence": int,
            "with_concentric_evidence": int,
            "with_feature_evidence": int,
            "with_hierarchy_evidence": int,
            "signal_distribution": {signal_count: count},
            "signal_strength": {"strong": int, "medium": int, "weak": int}
        }
    },
    "supervision": {supervision_mapper_result},
    "targets": {target_constructor_result},
    "training_context": {
        "geometry_count": int,
        "topology_edges": int,
        "feature_count": int,
        "repetition_count": int,
        "concentric_groups": int,
        "hole_candidates": int,
        "slot_candidates": int,
        "radial_patterns": int
    },
    "statistics": {
        "supervision": {...},
        "targets": {...},
        "conditioning": {...},
        "final_dataset": {...},
        "context": {...}
    }
}
```

---

*End of Section 07.*
*All field names, line numbers, and algorithm details verified against direct code reading.*
