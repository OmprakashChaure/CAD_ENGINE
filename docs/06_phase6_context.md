# SECTION 06 — PHASE 6: ENGINEERING CONTEXT ORGANIZATION
# CAD_ENGINE Design Authority Document

---

## 6.1 PURPOSE

Phase 6 builds the structural context graph between feature candidates:
which candidates are spatially related, which form dependency trees,
and how ambiguity propagates through the system.

**Orchestrator:** `pipeline/context_pipeline.py` → `ContextPipeline.run()`
**Called from:** `main.py` line 194-195
**Inputs:** `feature_result` (Phase 4) + `refinement_result` (Phase 5)

---

## 6.2 SUB-COMPONENT: CANDIDATE RELATIONSHIP BUILDER

**File:** `core/features/candidate_relationship_builder.py`
**Class:** `CandidateRelationshipBuilder`

### Purpose

Builds an adjacency structure between feature candidates based on
structural relationships identified in previous phases:
- Radial pattern → hole candidate relationships (from Phase 5 hierarchy)
- Repetition group membership (shared signature)
- Spatial proximity (candidates in the same topology region)

### Output

```python
{
    "relationships": [
        {
            "relationship_id": "rel_00001",
            "source_candidate_id": str,
            "target_candidate_id": str,
            "relationship_type": str
        }
    ],
    "adjacency": {candidate_id: [adjacent_candidate_ids]},
    "statistics": {
        "total_relationships": int,
        "connected_candidates": int
    }
}
```

---

## 6.3 SUB-COMPONENT: CONTEXT CLUSTER ANALYZER

**File:** `core/features/context_cluster_analyzer.py`
**Class:** `ContextClusterAnalyzer`

### Purpose

Groups feature candidates into "clusters" of strongly related candidates.
Each cluster represents a functionally cohesive group of features
(e.g., a bolt circle + its radial pattern + individual hole candidates).

### Algorithm

Connected component analysis on the `adjacency` graph from
CandidateRelationshipBuilder. All candidate_ids not connected to any
other candidate form single-element clusters.

### Input

- `adjacency`: the relationship adjacency from CandidateRelationshipBuilder
- `all_candidate_ids`: complete list of all candidate IDs (from ContextPipeline._collect_all_candidate_ids())

The `_collect_all_candidate_ids()` method (line 132-147) collects from:
- `feature_result["hole_candidates"]["hole_candidates"]`
- `feature_result["slot_candidates"]["slot_candidates"]`
- `feature_result["radial_patterns"]["radial_patterns"]`

### Output

```python
{
    "clusters": [
        {
            "cluster_id": "cl_00001",
            "candidate_ids": [...],
            "size": int
        }
    ],
    "statistics": {"total_clusters": int, "largest_cluster_size": int}
}
```

---

## 6.4 SUB-COMPONENT: RELATIONSHIP CONFIDENCE MANAGER

**File:** `core/features/relationship_confidence_manager.py`
**Class:** `RelationshipConfidenceManager`

### Purpose

Assigns confidence scores to candidate relationships by propagating
the per-candidate confidence scores from Phase 5 to the relationships
between them.

If candidate A has confidence 0.9 and candidate B has confidence 0.7,
their relationship confidence is typically computed as:
`rel_confidence = min(confidence_A, confidence_B)` or geometric mean.

### Output

```python
{
    "scored_relationships": [
        {
            "relationship_id": str,
            "confidence": float
        }
    ],
    "statistics": {"total_scored": int}
}
```

---

## 6.5 SUB-COMPONENT: STRUCTURAL DEPENDENCY MAPPER

**File:** `core/features/structural_dependency_mapper.py`
**Class:** `StructuralDependencyMapper`

### Purpose

Maps the dependency structure between features — which features depend
on others for their geometric definition.

Example: A radial pattern's center may be defined by the part's central bore.
The bolt circle DEPENDS on the bore location. This dependency is a structural
engineering fact, not a semantic interpretation.

### Input

- `feature_result` (Phase 4) — the candidates
- `hierarchy_result` (Phase 5) — the parent-child hierarchy

### Output

```python
{
    "dependencies": [
        {
            "dependent_id": str,
            "dependency_id": str,
            "dependency_type": str
        }
    ],
    "statistics": {"total_dependencies": int}
}
```

---

## 6.6 SUB-COMPONENT: CONTEXTUAL AMBIGUITY PROPAGATOR

**File:** `core/features/contextual_ambiguity_propagator.py`
**Class:** `ContextualAmbiguityPropagator`

### Purpose

Propagates ambiguity from individual candidates to relationships and clusters.
If an ambiguous candidate is part of a relationship or cluster, those
structures are also flagged as ambiguity-affected.

### Input

- `scored_relationships` — from RelationshipConfidenceManager
- `ambiguity_result` — from Phase 5 StructuralAmbiguityTracker
- `clusters` — from ContextClusterAnalyzer

### Output

```python
{
    "ambiguous_relationships": [...],
    "ambiguous_clusters": [...],
    "statistics": {
        "total_ambiguous_relationships": int,
        "total_ambiguous_clusters": int
    }
}
```

---

## 6.7 PHASE 6 OUTPUT CONTRACT

```python
{
    "relationships": {relationship_result},
    "clusters": {cluster_result},
    "relationship_confidence": {rel_confidence_result},
    "dependencies": {dependency_result},
    "ambiguity_propagation": {propagation_result},
    "statistics": {
        "relationships": {...},
        "clusters": {...},
        "relationship_confidence": {...},
        "dependencies": {...},
        "ambiguity_propagation": {...}
    }
}
```

**Note:** Phase 6 output (`context_result`) is passed to `DatasetPipeline.run()`
as the `context_result` parameter (main.py line 232) but the DatasetPipeline.run()
method signature accepts it optionally — it is not currently used in the core
dataset assembly logic. The `context_result` is included for completeness and
future use.

---

*End of Section 06.*
