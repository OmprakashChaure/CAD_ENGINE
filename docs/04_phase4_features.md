    # SECTION 04 — PHASE 4: FEATURE CANDIDATE DETECTION
    # CAD_ENGINE Design Authority Document

    ---

    ## 4.1 PURPOSE

    Phase 4 applies engineering pattern recognition to identify geometric structures
    that correspond to manufacturable features: holes, slots, and radial patterns.
    It also analyzes bilateral symmetry.

    **Orchestrator:** `pipeline/feature_pipeline.py` → `FeaturePipeline.run()`
    **Called from:** `main.py` line 152-155
    **Inputs:** `kept_entities` (Phase 1) + `structural_result` (Phase 3)

    ---

    ## 4.2 SUB-COMPONENT: HOLE CANDIDATE DETECTOR

    **File:** `core/features/hole_candidate_detector.py`

    ### What is a Hole Candidate?

    A "hole candidate" is a concentric geometry system that could represent a hole,
    boss, bore, pin, or any circular feature. The pipeline does NOT label it as
    a specific manufacturing feature — it labels it as a "candidate".

    ### Input

    The hole detector receives the full `concentric_result` from Phase 3,
    which contains the pre-computed concentric groups.

    ### Candidate Types

    | Type | Condition | Mechanical Interpretation |
    |------|-----------|--------------------------|
    | `single_radius` | 1 circle at a center | Simple through-hole or boss |
    | `multi_radius` | 2+ circles at a center | Counterbore, countersink, boss+hole |

    ### Output Structure per Candidate

    ```python
    {
        "candidate_id": "hc_00001",
        "candidate_type": "single_radius" | "multi_radius",
        "center": [x, y],
        "entity_ids": [entity_id, ...],
        "radii": [r1, r2, ...],           # sorted ascending
        "radius_count": int
    }
    ```

    ---

    ## 4.3 SUB-COMPONENT: SLOT CANDIDATE DETECTOR

    **File:** `core/features/slot_candidate_detector.py`
    **Class:** `SlotCandidateDetector`

    ### What is a Slot Candidate?

    An elongated closed contour with aspect ratio >= 2.0. In manufacturing:
    slots allow adjustment range for bolts, provide access openings, or serve
    as lightening features.

    ### Detection Criteria

    Applies to CLOSED LWPOLYLINE and POLYLINE entities:
    - Bounding box computed from `geometry["points"]`
    - Aspect ratio: `max(width, height) / min(width, height)`
    - Threshold: `aspect_threshold = 2.0` (from `configs/thresholds.yaml` → `slot_aspect_ratio`)

    ### Output Structure per Candidate

    ```python
    {
        "candidate_id": "sc_00001",
        "entity_id": str,
        "candidate_type": "slot",
        "aspect_ratio": float,
        "width": float,
        "height": float
    }
    ```

    ---

    ## 4.4 SUB-COMPONENT: RADIAL PATTERN DETECTOR

    **File:** `core/features/radial_pattern_detector.py`
    **Class:** `RadialPatternDetector`

    ### What is a Radial Pattern?

    N hole candidates of equal hole radius, arranged at equal angular spacing
    around a common center point. This corresponds to a bolt circle (PCD — Pitch Circle
    Diameter) in mechanical engineering.

    ### Algorithm Detail

    **Input:** `single_radius` hole candidates only (multi_radius excluded — line 83-87)

    **Step 1: Group by hole radius** (`_group_by_radius()`, line 129-154)
    Sorts candidates by `radii[0]` (hole radius).
    Groups adjacent candidates where relative radius difference <= `RADIUS_TOLERANCE = 0.02` (2%).

    **Step 2: Check circular arrangement** (`_detect_circular_arrangement()`, line 156-218)
    For each radius group of size >= `MIN_RADIAL_COUNT = 3`:

    1. Compute centroid of candidate centers:
    ```python
    cx = sum(p[0] for p in centers) / len(centers)
    cy = sum(p[1] for p in centers) / len(centers)
    ```

    2. Compute distance from centroid to each candidate:
    ```python
    d = sqrt((p[0]-cx)^2 + (p[1]-cy)^2)
    ```

    3. Check uniform radial distance — spread tolerance 10%:
    ```python
    spread = (max(distances) - min(distances)) / avg_dist
    if spread > 0.1: return None  # Not on common circle
    ```

    4. Compute angles and check equal spacing:
    ```python
    angle = math.degrees(math.atan2(p[1] - cy, p[0] - cx))
    ```
    Sorts angles, computes consecutive differences.
    Equal spacing check: `all(abs(s - avg_spacing) < ANGLE_TOLERANCE_DEG for s in spacings)`
    where `ANGLE_TOLERANCE_DEG = 5.0` degrees.

    ### Output Structure per Pattern

    ```python
    {
        "pattern_id": "rp_00001",
        "center": [cx, cy],              # centroid of hole centers
        "pattern_radius": float,          # avg distance from center to holes
        "member_candidate_ids": [...],
        "member_count": int,
        "angular_spacing_deg": float | None   # None if spacing not equal
    }
    ```

    ---

    ## 4.5 SUB-COMPONENT: SYMMETRY ANALYZER

    **File:** `core/features/symmetry_analyzer.py`
    **Class:** `SymmetryAnalyzer`

    ### What Symmetry Means

    Bilateral mirror symmetry — the drawing contains geometry that is mirrored
    about a horizontal or vertical axis. Common in symmetric plates, flanges, brackets.

    ### Algorithm

    For each pair of entities of the same type:
    1. Checks if their positions are mirror-symmetric about the bounding box midline
    (horizontal or vertical axis)
    2. Tolerance: `self.tolerance = 0.01` (from FeaturePipeline line 90)

    ### Output

    ```python
    {
        "symmetry_groups": [...],
        "statistics": {
            "total_groups": int
        }
    }
    ```

    ---

    ## 4.6 SUB-COMPONENT: FEATURE REGION GROUPER

    **File:** `core/features/feature_region_grouper.py`
    **Class:** `FeatureRegionGrouper`

    ### Purpose

    Associates each feature candidate (hole, slot, radial pattern) with
    the topology region it belongs to. This allows downstream reasoning to
    understand which features are "in the same part of the drawing".

    ### Algorithm

    For each candidate, looks up which region contains the candidate's
    constituent entity_ids using the region membership lookup from Phase 3.

    ---

    ## 4.7 PHASE 4 OUTPUT CONTRACT

    ```python
    {
        "hole_candidates": {
            "hole_candidates": [{candidate_id, candidate_type, center, entity_ids, radii, radius_count}],
            "statistics": {"total_candidates": int}
        },
        "slot_candidates": {
            "slot_candidates": [{candidate_id, entity_id, candidate_type, aspect_ratio, width, height}],
            "statistics": {"total_candidates": int}
        },
        "radial_patterns": {
            "radial_patterns": [{pattern_id, center, pattern_radius, member_candidate_ids, member_count, angular_spacing_deg}],
            "statistics": {"total_patterns": int, "candidates_analyzed": int, "radius_groups_found": int}
        },
        "symmetry": {
            "symmetry_groups": [...],
            "statistics": {"total_groups": int}
        },
        "feature_regions": {grouping_result},
        "statistics": {
            "holes": {...},
            "slots": {...},
            "radial_patterns": {...},
            "symmetry": {...},
            "feature_regions": {...}
        }
    }
    ```

    **Key fields consumed downstream:**
    - `hole_candidates` → `RadialPatternDetector` (within Phase 4, sequential)
    - `hole_candidates` → `ContextPackager` (Phase 7) for feature_membership
    - `slot_candidates` → `ContextPackager` (Phase 7) for feature_membership
    - `hole_candidates` → `RepeatedPatternConsolidator` (Phase 5)

    ---

    *End of Section 04.*
