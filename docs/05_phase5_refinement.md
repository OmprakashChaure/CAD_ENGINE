# SECTION 05 — PHASE 5: FEATURE CANDIDATE REFINEMENT
# CAD_ENGINE Design Authority Document

---

## 5.1 PURPOSE

Phase 5 takes the raw feature candidates from Phase 4 and applies five
refinement operations: confidence scoring, structural hierarchy, conflict
detection, repetition consolidation, and explicit ambiguity tracking.

**Orchestrator:** `pipeline/refinement_pipeline.py` → `RefinementPipeline.run()`
**Called from:** `main.py` line 174-175
**Input:** `feature_result` (Phase 4 output)

No geometry is modified. No entities are removed. The output is additional
metadata about candidate quality, organization, and uncertainty.

---

## 5.2 SUB-COMPONENT: CANDIDATE CONFIDENCE ANALYZER

**File:** `core/features/candidate_confidence_analyzer.py`
**Class:** `CandidateConfidenceAnalyzer`

### Purpose

Assigns a numerical confidence score to each feature candidate.
Higher confidence = more structural evidence supporting the candidate's validity.

### Confidence Signals

Scoring is based on structural observations:
- Number of entities in the candidate (more entities = higher confidence)
- Presence of concentric structure
- Aspect ratio (for slots)
- Radius count (for holes — multi_radius is higher confidence than single_radius)

### Output

```python
{
    "confidence_scores": [
        {
            "candidate_id": str,
            "confidence": float,      # 0.0 to 1.0
            "signals": {...}
        }
    ],
    "statistics": {"total_scored": int}
}
```

---

## 5.3 SUB-COMPONENT: FEATURE HIERARCHY BUILDER

**File:** `core/features/feature_hierarchy_builder.py`
**Class:** `FeatureHierarchyBuilder`

### Purpose

Builds parent-child relationships between feature candidates.
Example: a radial pattern CONTAINS multiple hole candidates.
The pattern is the parent; the holes are children.

### Algorithm

Inspects `radial_patterns` — each radial pattern references
`member_candidate_ids` which are hole candidate IDs.
This establishes the radial_pattern → hole_candidates hierarchy.

### Output

```python
{
    "hierarchy_tree": [
        {
            "parent_id": str,
            "parent_type": str,
            "children_ids": [...],
            "depth": int
        }
    ],
    "statistics": {"total_relationships": int}
}
```

---

## 5.4 SUB-COMPONENT: CANDIDATE CONFLICT RESOLVER

**File:** `core/features/candidate_conflict_resolver.py`
**Class:** `CandidateConflictResolver`

### Purpose

Detects cases where the same entity_id appears in multiple feature candidates.
This is a "conflict" — the same geometry has been claimed by different candidate
detection algorithms.

### Detection Strategy

Builds a mapping of `entity_id → [candidate_ids that claim this entity]`.
Any entity claimed by 2+ candidates is flagged as conflicting.

### Behavior

Conflicts are DETECTED but NOT resolved. The ambiguity is preserved.
The model receives BOTH competing interpretations as input context.

### Output

```python
{
    "conflicts": [
        {
            "entity_id": str,
            "conflicting_candidate_ids": [...],
            "conflict_type": str
        }
    ],
    "statistics": {"total_conflicts": int}
}
```

---

## 5.5 SUB-COMPONENT: REPEATED PATTERN CONSOLIDATOR

**File:** `core/features/repeated_pattern_consolidator.py`
**Class:** `RepeatedPatternConsolidator`

### Purpose

Identifies groups of feature candidates that are geometrically identical
(same type + same dimensions). These are "repetition groups" — when a
drawing has 4 identical M8 clearance holes, they form one repetition group.

### Signature Construction

For each candidate, builds a deterministic signature from its geometric properties:
- Hole: `("hole", tuple(sorted(rounded_radii)))`
- Slot: `("slot", round(aspect_ratio, precision))`
- Rounded to `precision=3` decimal places (configurable via `RefinementPipeline` config)

Candidates with matching signatures form a repetition group.

### Output

```python
{
    "repetition_groups": [
        {
            "group_id": "rg_00001",
            "signature": str,
            "candidate_ids": [...],
            "repetition_count": int
        }
    ],
    "statistics": {
        "total_repetition_groups": int,
        "total_repeated_candidates": int
    }
}
```

**This is critical for ML training:** A repetition group is evidence that
a missing dimension can be inferred from a sibling in the same group.
ContextPackager (Phase 7) propagates repetition membership to entity level.

---

## 5.6 SUB-COMPONENT: STRUCTURAL AMBIGUITY TRACKER

**File:** `core/features/structural_ambiguity_tracker.py`
**Class:** `StructuralAmbiguityTracker`

### Purpose

Tracks candidates whose geometric interpretation is genuinely ambiguous.
A candidate is "ambiguous" when:
- Its confidence score is below the `threshold=0.5`
- OR it is involved in a conflict with another candidate

### Behavior

Ambiguities are PRESERVED — never force-resolved.
The model training data explicitly includes ambiguous samples,
so the model learns that not every geometric structure has a clear answer.

### Output

```python
{
    "ambiguous_candidates": [
        {
            "candidate_id": str,
            "ambiguity_reason": str,
            "confidence": float
        }
    ],
    "statistics": {"total_ambiguous": int}
}
```

---

## 5.7 PHASE 5 OUTPUT CONTRACT

```python
{
    "confidence": {confidence_result},
    "hierarchy": {hierarchy_result},
    "conflicts": {conflict_result},
    "repetitions": {
        "repetition_groups": [{group_id, signature, candidate_ids, repetition_count}],
        "statistics": {
            "total_repetition_groups": int,
            "total_repeated_candidates": int
        }
    },
    "ambiguity": {ambiguity_result},
    "statistics": {
        "confidence": {...},
        "hierarchy": {...},
        "conflicts": {...},
        "repetitions": {...},
        "ambiguity": {...}
    }
}
```

**Key fields consumed downstream:**
- `repetitions.repetition_groups` → `ContextPackager` (Phase 7)
  for repetition_group lookup
- `confidence` → `RelationshipConfidenceManager` (Phase 6)
- `hierarchy` → `StructuralDependencyMapper` (Phase 6)
- `ambiguity` → `ContextualAmbiguityPropagator` (Phase 6)

---

*End of Section 05.*
