# SECTION 02 — PHASE 2: TOPOLOGY GRAPH CONSTRUCTION
# CAD_ENGINE Design Authority Document

---

## 2.1 PURPOSE

Phase 2 converts the flat list of normalized geometry entities into a
topological graph — an explicit representation of which entities are
physically connected to which other entities.

**Orchestrator:** `pipeline/topology_pipeline.py` → `TopologyPipeline.run()`
**Called from:** `main.py` line 110-111
**Input:** `extraction_result["entities"]` (kept entities from Phase 1)

---

## 2.2 SUB-COMPONENT: VERTEX INDEXER

**File:** `core/grouping/vertex_indexer.py`
**Class:** `VertexIndexer`

### Core Principle

Only ENDPOINTS participate in topology. Centers of circles and arcs are NOT
connection points. This is documented explicitly in the source code:
"CIRCLE: no endpoints (closed curve, no connection points)" (line 106-107)

### Endpoint Extraction by Entity Type (line 58-109)

| Entity Type | Endpoints Extracted |
|-------------|---------------------|
| LINE | `geometry["start"]`, `geometry["end"]` |
| LWPOLYLINE | All `geometry["points"]` vertices |
| POLYLINE | All `geometry["points"]` vertices |
| ARC | Computed from center + radius + angles |
| CIRCLE | NONE — no topology participation |
| DIMENSION, TEXT, MTEXT | NONE — no geometry |

### ARC Endpoint Computation (line 89-104)

ARC endpoints are computed analytically from polar to Cartesian:
```
start_point = (center.x + radius * cos(radians(start_angle)),
               center.y + radius * sin(radians(start_angle)))
end_point   = (center.x + radius * cos(radians(end_angle)),
               center.y + radius * sin(radians(end_angle)))
```
Angles are in degrees CCW from +X axis (DXF convention).

### Coordinate Snapping (line 44-49)

```python
def _snap_vertex(self, x, y):
    return (round(x, self.precision), round(y, self.precision))
```

Default precision: `VERTEX_PRECISION = 4` (verified line 25, also line 53 of topology_pipeline.py)
Snapping tolerance: 10^-4 drawing units = 0.1 micrometer for millimeter drawings.

### Vertex ID Assignment (line 51-56)

```python
def _get_vertex_id(self, key):
    if key not in self.vertex_ids:
        self._counter += 1
        self.vertex_ids[key] = f"vtx_{self._counter:05d}"
    return self.vertex_ids[key]
```

IDs are stable within a run (deterministic sequential assignment).

### Shared Vertex Definition (line 137-147)

A vertex is "shared" when `len(entity_ids) >= 2` — at least two distinct
entities have an endpoint at the same snapped coordinate.
Vertices touched by only one entity are "orphan" vertices (not in shared_vertices).

### VertexIndexer Output

```python
{
    "vertex_map": { (rx,ry): [entity_id, ...] },     # all vertices
    "vertex_ids": { (rx,ry): "vtx_00001" },           # stable IDs
    "shared_vertices": {                               # only 2+ entity vertices
        "vtx_00001": {
            "vertex_id": "vtx_00001",
            "x": float, "y": float,
            "connected_entities": [entity_id, ...]
        }
    },
    "statistics": {
        "total_vertices": int,
        "shared_vertices": int,
        "orphan_vertices": int,
        "entities_processed": int
    }
}
```

---

## 2.3 SUB-COMPONENT: ADJACENCY BUILDER

**File:** `core/grouping/adjacency_builder.py`
**Class:** `AdjacencyBuilder`

### Core Principle

Adjacency is ONLY derived from shared vertices. No distance heuristics.
No brute-force proximity checks. Two entities are adjacent if and only if
they share at least one snapped vertex coordinate.

### Hub Constraint (line 64-71)

A vertex with `len(entity_ids) > max_hub_size` is SKIPPED entirely.
Default: `MAX_HUB_SIZE = 8` (configured via `TopologyPipeline` at line 61).

**Engineering rationale:** In real DXF files, a vertex with 10+ connections
usually indicates overlapping geometry at the drawing origin or a complex
joint that cannot be resolved geometrically. Rather than generate incorrect
dense connectivity, the hub is excluded.

### Edge Generation (line 73-92)

For each shared vertex, generates all pairwise edges between connected entities:
```python
for i in range(len(entity_ids)):
    for j in range(i + 1, len(entity_ids)):
        pair = (min(src, tgt), max(src, tgt))  # canonical ordering
        if pair in seen_pairs: continue
        seen_pairs.add(pair)
        edges.append({...})
        adjacency_list[pair[0]].add(pair[1])
        adjacency_list[pair[1]].add(pair[0])
```

Deduplication uses canonical pair ordering: `(min(a,b), max(a,b))`.
This ensures each undirected edge appears exactly once regardless of
the order entities appear in the vertex's entity list.

### Adjacency List Format (line 94-98)

Sets are converted to sorted lists for deterministic output:
```python
adjacency_sorted = {k: sorted(list(v)) for k, v in adjacency_list.items()}
```

### AdjacencyBuilder Output

```python
{
    "edges": [
        {
            "source_entity_id": str,
            "target_entity_id": str,
            "shared_vertex_id": str
        }
    ],
    "adjacency_list": {entity_id: [connected_entity_ids]},
    "statistics": {
        "total_edges": int,
        "connected_entities": int,
        "skipped_hub_vertices": int,
        "max_hub_size_threshold": int
    }
}
```

---

## 2.4 ORPHAN DETECTION

**In:** `TopologyPipeline._detect_orphans()` (line 93-105)

```python
all_ids = {e["entity_id"] for e in entities}
connected_ids = set(adjacency_list.keys())
orphans = sorted(all_ids - connected_ids)
return orphans
```

An "orphan" entity has no topology connections — it does not appear in the
adjacency_list as either a source or target. Orphans include:
- Standalone circles (no endpoint to share — topologically isolated)
- Very short lines not snapping to any other endpoint
- Text/Dimension entities (no endpoints extracted)

Orphan entity IDs are reported in the output but NOT removed.

---

## 2.5 PHASE 2 OUTPUT CONTRACT

```python
{
    "shared_vertices": {vertex_id: {vertex_id, x, y, connected_entities}},
    "edges": [{source_entity_id, target_entity_id, shared_vertex_id}],
    "adjacency_list": {entity_id: [entity_id, ...]},
    "orphan_entities": [entity_id, ...],
    "statistics": {
        "total_vertices": int,
        "shared_vertices": int,
        "orphan_vertices": int,
        "entities_processed": int,
        "total_edges": int,
        "connected_entities": int,
        "skipped_hub_vertices": int,
        "max_hub_size_threshold": int,
        "orphan_entities": int,
        "total_input_entities": int
    }
}
```

**Key field consumed downstream:**
- `adjacency_list` → ContextPackager (Phase 7) for neighbor dimension lookup
- `adjacency_list` → ContourExtractor (Phase 3) for chain following
- `edges` → LoopDetector (Phase 3) for cycle detection
- `orphan_entities` → reported in statistics

---

*End of Section 02.*
*All line numbers verified against direct code reading.*
