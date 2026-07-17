# SECTION 03 — PHASE 3: STRUCTURAL ENGINEERING RECOGNITION
# CAD_ENGINE Design Authority Document

---

## 3.1 PURPOSE

Phase 3 takes topology (Phase 2 output) and extracts higher-order structural
patterns: contours (chains of connected geometry), loops (closed contours),
concentric geometry systems, disconnected topology regions, and containment hierarchy.

**Orchestrator:** `pipeline/structural_pipeline.py` → `StructuralPipeline.run()`
**Called from:** `main.py` line 130-133
**Inputs:** `kept_entities` (Phase 1) + `topology_result` (Phase 2)

---

## 3.2 SUB-COMPONENT: CONTOUR EXTRACTOR

**File:** `core/grouping/contour_extractor.py`

### What is a Contour?

A contour is a topologically-connected chain of geometry entities.
It is NOT necessarily a closed loop — it is any sequence of entities
connected endpoint-to-endpoint via the topology graph.

In mechanical drawings: the outer profile of a part forms one or more contours.
Holes inside the part form separate contours.

---

## 3.3 SUB-COMPONENT: LOOP DETECTOR

**File:** `core/grouping/loop_detector.py`

### What is a Loop?

A loop is a closed contour — a contour where the chain forms a complete cycle.
In mechanical drawings: the outer boundary is a loop. Each internal hole outline is a loop.

Loops are detected using cycle detection algorithms on the topology graph.
The loop_detector receives contours from ContourExtractor and verifies
which are topologically closed (first entity endpoint == last entity endpoint via the graph).

---

## 3.4 SUB-COMPONENT: CONCENTRIC GROUPING

**File:** `core/grouping/concentric_grouping.py`
**Class:** `ConcentricGrouping`

### What Concentricity Means in This Pipeline

Two circles or arcs are concentric when their centers match within coordinate
snapping precision. This is a pure geometric test — no semantic interpretation.

### Algorithm (detect() method)

**Step 1: Extract center-bearing entities** (line 144-182)
- Processes only `CIRCLE` and `ARC` entity types
- Extracts `center` and `radius` from geometry
- Skips entities with `radius <= 0` or `center is None`

**Step 2: Build center map** (line 87-94)
```python
center_key = (round(center[0], self.precision),
              round(center[1], self.precision))
center_map[center_key].append(entry)
```
Precision: `CENTER_PRECISION = 4` (same as vertex snapping)

**Step 3: Form groups** (line 96-121)
Only centers with `len(entries) >= 2` form a concentric group.
Single circles/arcs are "ungrouped".

Entities within each group are sorted by radius ascending:
```python
entries_sorted = sorted(entries, key=lambda e: e["radius"])
```

**Step 4: Output**
```python
{
    "concentric_groups": [
        {
            "group_id": "conc_00001",
            "center": [x, y],
            "entity_ids": [id1, id2, ...],   # sorted by radius ascending
            "radii": [r1, r2, ...],           # sorted ascending
            "count": int
        }
    ],
    "ungrouped_circles": [entity_id, ...],
    "statistics": {
        "total_groups": int,
        "total_circle_arc_entities": int,
        "grouped_entities": int,
        "ungrouped_entities": int
    }
}
```

**IMPORTANT LIMITATION:** CIRCLE centers do NOT participate in the topology vertex
index (VertexIndexer explicitly excludes them at line 106-107 of vertex_indexer.py).
This means concentric circles are topologically ORPHAN entities — they have no
topology connections. Concentric detection happens INDEPENDENTLY from topology.

---

## 3.5 SUB-COMPONENT: REGION ANALYZER

**File:** `core/grouping/region_analyzer.py`
**Class:** `RegionAnalyzer`

### What is a Region?

A topology "region" is a set of entities that are mutually reachable through the
adjacency graph — a connected component. Two entities in different regions have
no topological connection path between them.

**Engineering meaning:** A complex plate drawing may have:
- Region 1: the outer profile (one large connected component)
- Region 2: a bolt-hole group (four circles forming a separate component)
- Region 3: a slot outline (separate connected subgraph)

### Algorithm

Connected component analysis via BFS/DFS on the adjacency_list.
Each disconnected component is one region.

**Output:**
```python
{
    "regions": [
        {
            "region_id": "reg_00001",
            "entity_ids": [...],
            "size": int
        }
    ],
    "statistics": {
        "total_regions": int,
        "largest_region_size": int
    }
}
```

---

## 3.6 SUB-COMPONENT: CONTOUR HIERARCHY

**File:** `core/grouping/contour_hierarchy.py`
**Class:** `ContourHierarchy`

### What Containment Hierarchy Means

In engineering drawings, features appear INSIDE other features:
- A hole circle is INSIDE the outer plate boundary
- A slot is INSIDE the part profile
- A counterbore inner circle is INSIDE the outer bolt circle

### Algorithm (analyze() method)

**Step 1: Extract closed polylines** (line 53-78)
Only `LWPOLYLINE` and `POLYLINE` entities with `closed=True` and `len(points) >= 3` participate.
For each, computes: `xmin, xmax, ymin, ymax, area = (xmax-xmin)*(ymax-ymin)`.

**Step 2: Sort by area descending** (line 87)
Larger contours are potential parents.

**Step 3: Determine parent-child relationships** (line 100-120)
For each contour, finds the smallest parent that fully contains its bounding box:
```python
if (parent.xmin <= child.xmin and parent.xmax >= child.xmax and
    parent.ymin <= child.ymin and parent.ymax >= child.ymax and
    parent.area > child.area):
    if parent.area < best_area:
        best_area = parent.area
        best_parent = parent.entity_id
```

Containment test is BOUNDING BOX only — NOT true polygon containment.
This is documented in the class docstring: "bounding-box containment as a conservative proxy".

**Step 4: Compute nesting depth** (line 128-136)
Walk parent chain upward, count steps:
```python
while hierarchy[current]["parent_id"] is not None:
    depth += 1
    current = hierarchy[current]["parent_id"]
    if depth > 10: break  # Safety cap against cycles
```

**Output per entity:**
```python
{
    "entity_id": str,
    "contour_role": "outer" | "inner" | "isolated",
    "parent_id": str | None,
    "children_ids": [...],
    "nesting_depth": int
}
```

**LIMITATION:** Only CLOSED LWPOLYLINE/POLYLINE participate in hierarchy.
CIRCLE entities (topologically orphaned) do NOT participate in hierarchy analysis.
A hole represented as a CIRCLE is never assigned "inner" role — it remains isolated.

---

## 3.7 PHASE 3 OUTPUT CONTRACT

```python
{
    "contours": {contour_result dict},
    "loops": {loop_result dict},
    "concentric_groups": {
        "concentric_groups": [...],
        "ungrouped_circles": [...],
        "statistics": {...}
    },
    "regions": {
        "regions": [...],
        "statistics": {...}
    },
    "contour_hierarchy": {
        "hierarchy": [...],
        "statistics": {"total_contours": int, "outer": int, "inner": int}
    },
    "statistics": {
        "contours": {...},
        "loops": {...},
        "concentric": {...},
        "regions": {...},
        "hierarchy": {...}
    }
}
```

**Key fields consumed downstream:**
- `concentric_groups` → `HoleCandidateDetector` (Phase 4)
- `regions` → `FeatureRegionGrouper` (Phase 4)
- `regions` → `ContextPackager` (Phase 7) for region_size lookup
- `concentric_groups` → `ContextPackager` (Phase 7) for concentric_group lookup
- `contour_hierarchy` → `ContextPackager` (Phase 7) for contour hierarchy evidence

---

*End of Section 03.*
*All line numbers verified against direct code reading.*
