# SECTION 00 — MECHANICAL CONCEPT TO CODE MAPPING BRIDGE
# CAD_ENGINE Design Authority Document

---

## PURPOSE

This section maps every mechanical engineering concept present in the codebase to
the exact Python class, method, and data structure that implements it.

A Mechanical Engineer who reads this section will know exactly where to look in the
code when they see a concept from their discipline.

An AI/ML Engineer who reads this section will understand WHY the code is structured
the way it is — because mechanical engineering drawing conventions require it.

---

## 1. DXF ENTITY TYPES AND THEIR MECHANICAL MEANING

### 1.1 LINE

**Mechanical meaning:** A visible edge, a centerline, a hidden line, or a construction
line. In a 2D engineering drawing, any straight boundary between materials or between
visible and hidden space is a LINE.

**Code mapping:**
- Normalized by: `core/classifiers/geometry_normalizer.py` → `GeometryNormalizer._normalize_line()`
- Produces: `{"type": "LINE", "geometry": {"start": [x,y], "end": [x,y], "length": float}}`
- Length computed: `math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)` (line 355-358)
- Topological endpoints: used by `core/grouping/vertex_indexer.py` for connectivity

**Engineering drawing rule implemented:**
A LINE entity carries its engineering role NOT from its geometry but from its layer.
The layer_rules.yaml maps layer names (CENTER, HIDDEN, CONTINUOUS) to roles
(centerline, hidden_line, visible_edge). The geometry itself is layer-agnostic.

---

### 1.2 CIRCLE

**Mechanical meaning:** A hole cross-section, a boss, a pin, a shaft, or a bore.
In 2D engineering drawings, CIRCLE entities almost always represent features
that are circular in 3D: holes (which you look down into), bosses (which you look at),
or concentric structural features.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_circle()` (line 79-93)
- Produces: `{"type": "CIRCLE", "geometry": {"center": [x,y], "radius": float, "diameter": float, "area": float}}`
- Area computed: `math.pi * radius * radius`
- Concentric detection: `core/grouping/concentric_grouping.py` groups CIRCLEs sharing center
  within `round(center, precision=4)` tolerance

**Engineering drawing rule implemented:**
Two concentric CIRCLEs in a 2D drawing almost always represent a stepped hole,
a boss-and-counterbore, or a bearing seat. The ConcentricGrouping class detects this
structural pattern geometrically — it NEVER assumes what the concentric system means
mechanically.

---

### 1.3 ARC

**Mechanical meaning:** A fillet, a rounded corner, a partial bore, or an arc slot.
In engineering drawings, ARCs appear at corners (as fillets) and in slot ends.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_arc()` (line 99-112)
- Produces: `{"type": "ARC", "geometry": {"center": [x,y], "radius": float, "start_angle": float, "end_angle": float}}`
- Fillet detection threshold: `configs/thresholds.yaml` → `fillet_max_sweep: 120` degrees

**Engineering drawing rule implemented:**
An ARC with sweep angle ≤ 120° at the junction of two LINEs is a fillet.
An ARC with sweep ≈ 180° at the end of a slot is a slot-end.
The code preserves both raw geometry AND concentric membership so that
downstream feature detection can classify correctly.

---

### 1.4 LWPOLYLINE (Lightweight Polyline)

**Mechanical meaning:** The outer profile, a slot, or any compound boundary consisting
of connected line segments and arcs. LWPOLYLINE is the most efficient way AutoCAD
stores 2D part outlines. A bolted flange plate outer boundary is almost always an LWPOLYLINE.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_lwpolyline()` (line 118-153)
- CRITICAL: Each LWPOLYLINE vertex is stored as `(x, y, start_width, end_width, bulge)`
  The bulge is element `point[4]` — only extracted when `len(point) > 4`
- Bulge threshold: `abs(bulge) > 1e-6` → treated as arc segment
- Produces `arc_segments` list: `[{"index": int, "bulge": float, "direction": "ccw"|"cw"}]`

**Bulge formula reference (engineering mathematics):**
The bulge value `b` encodes an arc between two consecutive vertices.
- `b = tan(theta/4)` where `theta` is the arc's included angle
- `b > 0` → counterclockwise arc (CCW)
- `b < 0` → clockwise arc (CW)
- `b = 0` → straight line segment
- Radius: `R = |chord| * (1 + b^2) / (4 * |b|)`

NOTE: The current code PRESERVES the bulge value for downstream use but does NOT
decompose it into explicit arc geometry (center/radius). This is a deliberate
design choice — the bulge data is retained additively in `arc_segments`.

---

### 1.5 POLYLINE (Heavy Polyline)

**Mechanical meaning:** Identical to LWPOLYLINE but older DXF format.
POLYLINE stores vertices as separate VERTEX entities with DXF group code 42 for bulge.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_polyline()` (line 159-198)
- Vertices accessed via `entity.vertices` iterator
- Bulge accessed via: `getattr(vertex.dxf, "bulge", 0.0)` (handles missing attribute)
- Comment in code: "Preserve bulge value (DXF group code 42)" — line 171

---

### 1.6 DIMENSION

**Mechanical meaning:** A dimension annotation — a measurement attached to geometry
in the drawing. DIMENSIONs carry the actual manufacturing target values.
They are NOT just display annotations — they ARE the engineering specification.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_dimension()` (line 203-275)
- Dimension type decoded from `entity.dxf.dimtype & 7`:
  - 0 = linear, 1 = aligned, 2 = angular, 3 = diameter, 4 = radius,
    5 = angular_3point, 6 = ordinate
- Text symbol overrides: "Ø" or "ø" → diameter; "R" prefix → radius; "°" → angular
- Target points: `defpoint2`, `defpoint3`, `defpoint4`, `defpoint5` — these are the
  geometric reference points the dimension measures
- Numeric extraction: three fallback strategies:
  1. `parse_fractional_value()` — handles "1/2", "3 1/4" imperial fractions
  2. `entity.dxf.actual_measurement` — AutoCAD computed value
  3. Regex extraction: strip count prefix (e.g. "4X Ø8") then extract first number

**Engineering drawing rule implemented:**
Dimension entities in AutoCAD contain BOTH the displayed text AND geometric
reference points (defpoints). The reference points are the exact coordinates
being measured. The code uses BOTH to associate a dimension to the correct geometry.

---

### 1.7 TEXT / MTEXT

**Mechanical meaning:** Annotations, callouts, tolerance notes, material specifications,
thread callouts (M8x1.25), surface finish symbols. Some TEXT entities in drawings
duplicate dimension values — these are engineering values even though they are not
DIMENSION entities.

**Code mapping:**
- Normalized by: `GeometryNormalizer._normalize_text()` (line 281-347)
- MTEXT: uses `entity.plain_text()` to strip DXF formatting codes
- TEXT: uses `getattr(entity.dxf, "text", "")`
- `%%C` → `Ø` (diameter symbol translation, line 246 in semantic_pipeline.py)
- Text role classification:
  - `M<digit>` at start → `thread_callout`
  - Contains `±` → `tolerance`
  - Starts with `R` + digit → `radius_value`
  - Contains `Ø` → `diameter_value`
  - Contains `°` → `angle_value`
  - Has any digit → `dimension_value`
  - Otherwise → `annotation`

---

## 2. LAYER SYSTEM AND ENGINEERING ROLES

### 2.1 What Layers Mean in Engineering Drawings

In DXF files produced by mechanical CAD systems (AutoCAD, SolidWorks, etc.),
layers encode LINE TYPE and ENGINEERING ROLE:

| Layer/Linetype Convention | Engineering Meaning |
|--------------------------|---------------------|
| CONTINUOUS / solid | Visible edge — material boundary you can see |
| CENTER / CENTER2 | Centerline — axis of symmetry or rotation |
| HIDDEN / HIDDEN2 / DASHED | Hidden line — edge hidden behind material |
| PHANTOM | Construction line — reference geometry not part of the part |
| DIM / DIMENSION | Dimension annotation layer |

### 2.2 Code Implementation

**Config file:** `configs/layer_rules.yaml`

```yaml
linetype_roles:
  HIDDEN: hidden_line
  CENTER: centerline
  PHANTOM: construction_line
  CONTINUOUS: visible_edge

ignore_layers:
  - DEFPOINTS
  - VIEWPORT
  - TEXT
  - ANNOTATION
  - TITLE
  - BORDER
```

**Filter implementation:** `core/filters/layer_filter.py` → `LayerFilter.filter()`
- Loads `ignore_layers` from YAML at construction
- Normalizes layer names to UPPERCASE before comparison
- Entities on ignored layers are placed in `removed_entities` (NOT quarantined)

**Engineering rationale:** DEFPOINTS is AutoCAD's internal dimension attachment layer.
VIEWPORT entities are paper space viewports. Neither contains engineering geometry.

---

## 3. TOPOLOGICAL CONCEPTS AND CODE IMPLEMENTATION

### 3.1 Shared Vertex (Geometric Connectivity)

**Mechanical meaning:** Two edges in a 2D engineering drawing are connected when they
share an endpoint. A part's outer profile is a closed chain of connected edges.

**Code mapping:**
- `core/grouping/vertex_indexer.py` → `VertexIndexer.build()`
- Coordinate snapping: `round(x, 4), round(y, 4)` — 4 decimal places of precision
- Two vertices are "shared" when their rounded coordinates are identical
- Result: `shared_vertices` dict: `{(rx, ry): [entity_id_1, entity_id_2, ...]}`

**Engineering rationale:** In real DXF files produced from CAD software, endpoints
rarely have exact floating-point equality. A line ending at `(10.0000001, 5.0)` and
an arc starting at `(9.9999999, 5.0)` are the SAME point. Rounding to 4 decimal places
(0.1 micrometer for mm drawings) captures this while rejecting noise.

### 3.2 Hub Constraint

**Mechanical meaning:** In a clean mechanical drawing, most vertices are T-junctions
(3 edges meeting) or simple corners (2 edges meeting). Very rarely do 5+ edges share
a single vertex — if they do, it often indicates overlapping geometry or a complex joint.

**Code mapping:**
- `core/grouping/adjacency_builder.py` → `AdjacencyBuilder` with `max_hub_size=8`
- A vertex with >8 entities is treated as a "hub" — connections are added but
  no entity becomes a topology neighbor of all others through it
- Configured by: `TopologyPipeline` passes `max_hub_size=8` from config (line 61)

---

## 4. FEATURE CANDIDATE CONCEPTS

### 4.1 Hole Candidate

**Mechanical meaning:** A cylindrical hole, counterbore, or countersink.
In 2D top-view: appears as one or more concentric circles.
- Single circle = through-hole
- Two concentric circles = counterbore or countersink (larger outer, smaller inner)
- Three concentric circles = complex bore system (pilot + clearance + counterbore)

**Code mapping:**
- `core/features/hole_candidate_detector.py` → `HoleCandidateDetector.detect()`
- Input: concentric groups from `ConcentricGrouping`
- `candidate_type`:
  - `"single_radius"` → one circle (simple hole or isolated bore)
  - `"multi_radius"` → multiple concentric circles (counterbore system)

### 4.2 Slot Candidate

**Mechanical meaning:** An elongated slot used for adjustment, bolt access, or
clearance. In 2D: a closed outline with two parallel straight edges and semicircular ends.
The defining property: length ≥ 2× width (aspect ratio ≥ 2.0).

**Code mapping:**
- `core/features/slot_candidate_detector.py` → `SlotCandidateDetector.detect()`
- Aspect threshold: 2.0 (from `configs/thresholds.yaml` → `slot_aspect_ratio: 2.0`)
- Applied to: closed LWPOLYLINE or POLYLINE contours

### 4.3 Radial Pattern

**Mechanical meaning:** A bolt circle — N holes equally spaced around a common center
at equal radial distance. Appears in flanges, covers, and circular plates.

**Code mapping:**
- `core/features/radial_pattern_detector.py` → `RadialPatternDetector.detect()`
- Minimum count: 3 holes (constant `MIN_RADIAL_COUNT = 3`)
- Equal radius check: relative tolerance `RADIUS_TOLERANCE = 0.02` (2%)
- Equal angular spacing: `ANGLE_TOLERANCE_DEG = 5.0` degrees
- Algorithm: compute centroid of all candidate centers, check uniform radial distance,
  sort angles, check equal spacing between consecutive angles

---

## 5. SUPERVISION CONCEPTS (DIMENSION → GEOMETRY ASSOCIATION)

### 5.1 Target Point Proximity

**Mechanical meaning:** In AutoCAD, every DIMENSION entity stores "definition points"
(defpoints) — the exact coordinates on the geometry being measured. A linear dimension
measuring the distance between two holes stores the defpoints AT the hole centers.

**Code mapping:**
- `core/supervision/supervision_mapper.py` → `SupervisionMapper._match_by_target_points()`
- Extracts `target_points` from dimension geometry
- Computes Euclidean distance from each target point to each geometry reference point
- Tolerance: 1.0 drawing units (configurable via `association_tolerance` config key)
- Reference points per entity type:
  - LINE → start, end
  - CIRCLE/ARC → center
  - LWPOLYLINE/POLYLINE → first 4 vertices

### 5.2 Value Matching Fallback

**Mechanical meaning:** When defpoints are absent or corrupted, the dimension value
itself is evidence. If a dimension reads "50.0" and a line has computed length 50.0,
they are very likely associated.

**Code mapping:**
- `SupervisionMapper._match_by_value()`
- Tolerance: 1% relative (`ratio = abs(sup_value - comp_value) / comp_value < 0.01`)

---

## 6. LEAKAGE PREVENTION CONCEPT

### 6.1 What Leakage Means in This Context

**ML meaning:** If the target dimension value (the answer the model must predict)
is VISIBLE in the input context, the model learns to copy rather than reason.
This is data leakage — the model memorizes the answer location, not the engineering reasoning.

**Code mapping:**
- `core/supervision/inference_conditioner.py` → `InferenceConditioner._build_masked_context()`
- The target dimension type and value are REMOVED from `own_dimensions`
  in the visible context (line 159-165)
- Leakage audit checks both own dimensions AND neighbor dimensions
- `leakage_prevented` = True when the target value does NOT appear in `other_own`
- Neighbor dimensions with same value are KEPT but FLAGGED — because a neighbor
  having the same dimension may be VALID REASONING EVIDENCE from repetition patterns

---

*End of Section 00.*
*All file paths and line numbers verified against direct code reading.*
