# SECTION 01 — PHASE 1: DXF EXTRACTION & FILTERING
# CAD_ENGINE Design Authority Document

---

## 1.1 PURPOSE

Phase 1 is responsible for converting a raw DXF file into a clean, canonical list
of engineering entities suitable for downstream processing.

Phase 1 output: `extraction_result["entities"]` — a `List[Dict]` where each Dict
is a complete, normalized, layer-tagged, geometry-validated engineering entity.

**Orchestrator:** `pipeline/extraction_pipeline.py` → `ExtractionPipeline.run()`
**Called from:** `main.py` line 85-86

---

## 1.2 SUB-COMPONENT: DXF LOADER

**File:** `core/reader/dxf_loader.py`
**Class:** `DXFLoader`

### Loading Strategy (Two-Stage Fallback)

```python
# Stage 1: Standard load
document = ezdxf.readfile(str(self.dxf_path))

# Stage 2: Recovery load (if Stage 1 fails)
from ezdxf import recover
document, auditor = recover.readfile(str(self.dxf_path))
```

**Engineering rationale:** Real-world DXF files from manufacturing environments are
frequently damaged or contain non-conforming structures (AutoCAD internal inconsistencies,
export bugs from SolidWorks/CATIA). `ezdxf.recover.readfile()` is ezdxf's built-in
repair mechanism that can parse structurally compromised DXF files.

**Validation performed before load:**
1. File must exist: `self.dxf_path.exists()` → raises `FileNotFoundError`
2. Extension must be `.dxf`: `suffix.lower() != ".dxf"` → raises `ValueError`

**Return type:** `ezdxf.document.Drawing` — the full parsed DXF document object.

---

## 1.3 SUB-COMPONENT: ENTITY ITERATOR

**File:** `core/reader/entity_iterator.py`
**Class:** `EntityIterator`

### What This Does

Iterates through `document.modelspace()` — the primary engineering drawing space
in every DXF file. Paper space (drawing frame, title block, viewports) is NOT iterated.

### Supported Entity Types (line 15-27)

```
LINE, CIRCLE, ARC, LWPOLYLINE, POLYLINE, SPLINE,
TEXT, MTEXT, INSERT, DIMENSION, HATCH
```

Entities NOT in this set are silently skipped at the iterator level (debug log only).

### Entity ID Assignment

Each entity receives a stable, sequential ID:
```python
"entity_id": f"ent_{counter:05d}"
```
Counter increments for EVERY entity seen, even unsupported ones. IDs are stable
within a single pipeline run but NOT across runs (counter resets per invocation).

### Canonical Entity Dictionary Schema

Every yielded entity dictionary contains exactly these fields:

| Field | Source | Type |
|-------|--------|------|
| `entity_id` | `ent_{counter:05d}` | str |
| `source_file` | `dxf_path.name` | str |
| `entity_type` | `entity.dxftype().upper()` | str |
| `handle` | `entity.dxf.handle` | str (DXF internal ID) |
| `layer` | `normalize_layer(entity.dxf.layer)` | str (uppercased) |
| `linetype` | `getattr(entity.dxf, "linetype", None)` | str or None |
| `color` | `getattr(entity.dxf, "color", None)` | int or None |
| `geometry` | `GeometryNormalizer.normalize(entity)["geometry"]` | Dict or None |
| `supported` | `normalized["supported"]` | bool |
| `possible_overlap` | `False` | bool (default) |
| `overlap_confidence` | `0.0` | float (default) |

**CRITICAL NOTE:** `TEXT`, `MTEXT`, `DIMENSION`, `SPLINE`, `INSERT`, `HATCH`
entities yield `supported=False` from the normalizer, meaning their geometry
field is None. They are NOT silently dropped — they enter the filter chain and are
quarantined by `DegenerateFilter`, preserving them for future annotation extraction.
This design choice is explicitly documented in the source code comments (line 60-73).

---

## 1.4 SUB-COMPONENT: GEOMETRY NORMALIZER

**File:** `core/classifiers/geometry_normalizer.py`
**Class:** `GeometryNormalizer` (all static methods)

### Dispatch Table (normalize() method, line 25-54)

```python
entity_type = entity.dxftype()
if   entity_type == "LINE":       → _normalize_line()
elif entity_type == "CIRCLE":     → _normalize_circle()
elif entity_type == "ARC":        → _normalize_arc()
elif entity_type == "LWPOLYLINE": → _normalize_lwpolyline()
elif entity_type == "POLYLINE":   → _normalize_polyline()
elif entity_type == "DIMENSION":  → _normalize_dimension()
elif entity_type in ("TEXT","MTEXT"): → _normalize_text()
else: → {"type": type, "geometry": None, "supported": False}
```

### LINE normalization (line 60-73)

```python
{
    "type": "LINE",
    "geometry": {
        "start": [float(start.x), float(start.y)],
        "end":   [float(end.x), float(end.y)],
        "length": sqrt((p2.x-p1.x)^2 + (p2.y-p1.y)^2)
    },
    "supported": True
}
```

### CIRCLE normalization (line 79-93)

```python
{
    "type": "CIRCLE",
    "geometry": {
        "center":   [float(center.x), float(center.y)],
        "radius":   float(entity.dxf.radius),
        "diameter": radius * 2.0,
        "area":     math.pi * radius * radius
    },
    "supported": True
}
```

### ARC normalization (line 99-112)

```python
{
    "type": "ARC",
    "geometry": {
        "center":      [float(center.x), float(center.y)],
        "radius":      float(entity.dxf.radius),
        "start_angle": float(entity.dxf.start_angle),   # degrees CCW from +X
        "end_angle":   float(entity.dxf.end_angle)       # degrees CCW from +X
    },
    "supported": True
}
```

### LWPOLYLINE normalization (line 118-153)

Each vertex is `(x, y, start_width, end_width, bulge)` via `entity.get_points()`.
Bulge extraction: `point[4] if len(point) > 4 else 0.0`
Bulge threshold: `abs(bulge) > 1e-6` → arc segment present

```python
{
    "type": "LWPOLYLINE",
    "geometry": {
        "points": [[x,y], ...],
        "closed": bool(entity.closed),
        "has_arcs": bool,
        # if has_arcs:
        "arc_segments": [{"index": int, "bulge": float, "direction": "ccw"|"cw"}],
        "arc_count": int
    },
    "supported": True
}
```

**Bulge direction rule (implemented at line 134):**
- `bulge > 0` → `"ccw"` (counterclockwise arc)
- `bulge < 0` → `"cw"` (clockwise arc)

### DIMENSION normalization (line 203-275)

Three-stage numeric value extraction:
1. `parse_fractional_value(raw_text)` — handles imperial fractions like "1/2", "3 1/4"
2. `entity.dxf.actual_measurement` — AutoCAD computed measurement value
3. Regex extraction: strip count prefix `r"^\s*\d+\s*[Xx]\s+"`, then extract first float

Symbol-based type override (checked AFTER dimtype code):
- "Ø" or "ø" in text → `dim_type = "diameter"`
- Text starts with "R" + digit → `dim_type = "radius"`
- "°" in text → `dim_type = "angular"`

Target points extracted from DXF attributes: `defpoint2`, `defpoint3`, `defpoint4`, `defpoint5`

---

## 1.5 FILTER CHAIN

**Applied sequentially in:** `ExtractionPipeline.run()` (line 52-58)
**Order:** TextFilter → DegenerateFilter → DuplicateFilter → LayerFilter → BorderFilter

The output of each filter stage becomes the input of the next.
Quarantined entities accumulate across all stages but do NOT re-enter the active set.

### FilterResult Contract (schemas/geometry_schema.py, line 75-79)

```python
class FilterResult(BaseModel):
    kept_entities: List[Dict[str, Any]]
    quarantined_entities: List[FilteredEntity]
    removed_entities: List[FilteredEntity]
    statistics: FilterStatistics
```

### FilteredEntity Contract (line 57-60)

```python
class FilteredEntity(BaseModel):
    entity: Dict[str, Any]
    reason: str
    confidence: float = 0.5
```

---

### Filter 1: TextFilter (core/filters/text_filter.py)

**Purpose:** Route TEXT/MTEXT entities — keep supervision-bearing text, quarantine annotations.

**Supervision roles kept (SUPERVISION_ROLES set, line 21-28):**
`"dimension_value"`, `"diameter_value"`, `"radius_value"`, `"angle_value"`, `"tolerance"`, `"thread_callout"`

**Logic:**
- If entity is TEXT or MTEXT: check `geometry["text_role"]`
  - In SUPERVISION_ROLES → `kept`
  - Not in SUPERVISION_ROLES → `quarantined` with reason `"non_supervision_text:{role}"`
- All other entity types → pass through to `kept`

**Note:** DIMENSION entities are NOT TEXT — they pass through this filter untouched.

---

### Filter 2: DegenerateFilter (core/filters/degenerate_filter.py)

**Purpose:** Validate geometric integrity of all normalized entities.

**EPSILON constant:** `1e-6` (line 14)

**Decision matrix:**

| Condition | Action | Reason String |
|-----------|--------|---------------|
| `geometry is None` and `supported=False` | quarantine | `"unsupported_geometry_type:{type}"` |
| `geometry is None` and `supported=True` | **remove** | `"corrupted_geometry_null"` |
| LINE: `length < 0` | **remove** | `"negative_length"` |
| LINE: `length <= 1e-6` | quarantine | `"tiny_line"` |
| CIRCLE: `radius < 0` | **remove** | `"negative_radius"` |
| CIRCLE: `radius <= 1e-6` | quarantine | `"tiny_circle"` |
| ARC: `radius <= 1e-6` | quarantine | `"tiny_arc"` |
| LWPOLYLINE/POLYLINE: `len(points) < 2` | quarantine | `"invalid_polyline_too_few_points"` |
| Any validation exception | **remove** | `"geometry_validation_error: {exc}"` |
| All other cases | **keep** | — |

**CRITICAL DESIGN DECISION: quarantine vs remove**
- `remove` = entity is permanently discarded, only logged
- `quarantine` = entity is preserved in `quarantined_entities`, accessible downstream
- Default policy: "quarantine over remove when possible" (line 28)
- Only hard errors (impossible geometry) are removed

---

### Filter 3: DuplicateFilter (core/filters/duplicate_filter.py)

**Purpose:** Detect geometrically identical entities (common in exported DXF files).

**Signature construction:** From `geometry` dict only — NOT from layer or handle.
Rounding precision: 5 decimal places for coordinates.

**Signatures:**
- LINE: `("LINE", sorted_endpoints_tuple)` — direction-independent (line 56)
- CIRCLE: `("CIRCLE", center_tuple, radius)` (line 62-66)
- ARC: `("ARC", center_tuple, radius, start_angle_deg3, end_angle_deg3)` (line 71-78)
- LWPOLYLINE/POLYLINE: `(type, point_sequence_tuple, closed)` (line 83-93)
- Any entity with `geometry=None` → `None` signature → always KEPT

**Behavior:**
- First occurrence with a given signature → canonical, kept, stored in `self.seen`
- Subsequent occurrence with same signature → quarantined with `"exact_geometric_duplicate"`
- Tags on quarantined entity: `possible_overlap=True`, `overlap_confidence=1.0`
- Exception during signature building → kept (conservative, logged as warning)

---

### Filter 4: LayerFilter (core/filters/layer_filter.py)

**Purpose:** Remove entities on non-engineering layers.

**Config:** `configs/layer_rules.yaml` → `ignore_layers` list
```
DEFPOINTS, VIEWPORT, VIEW, TEXT, ANNOTATION, TITLE, BORDER
```

**Logic:** `entity["layer"].upper()` in `self.ignore_layers` → `removed` (NOT quarantined)

**NOTE:** LayerFilter is one of the two filters that use `removed` instead of `quarantined`.
Entities on ignored layers are definitively non-engineering content.

---

### Filter 5: BorderFilter (core/filters/border_filter.py)

**Purpose:** Detect drawing border/frame geometry and quarantine it.

**Two detection strategies:**

**Strategy 1 — Long Lines** (line 54-59):
- Threshold: `LARGE_LINE_THRESHOLD = 1000.0` drawing units
- Confidence: `min(0.6 + (length / 5000.0) * 0.3, 0.95)`

**Strategy 2 — Large Closed Polylines** (line 61-75):
- Checks: `geometry["closed"] == True`
- Computes polyline bounding box vs drawing bounding box
- Ratio threshold: `FRAME_AREA_RATIO = 0.85` (>85% of drawing area)
- Override: If `entity["layer"].upper() == "GEOMETRY"` → NOT a border
- Override: If polyline dimensions match any DIMENSION/TEXT value (1% tolerance) → NOT a border

**Drawing bounding box:** Computed from ALL entities before filtering begins.
Includes LINE endpoints, CIRCLE/ARC centers±radius, LWPOLYLINE points.

---

## 1.6 PHASE 1 OUTPUT CONTRACT

```python
{
    "entities": List[Dict],                # kept entities
    "quarantined_entities": List[Dict],    # .model_dump() of FilteredEntity
    "removed_entities": List[Dict],        # .model_dump() of FilteredEntity
    "filter_reports": [                    # one per filter stage
        {
            "filter": "TextFilter",
            "statistics": {
                "input_entities": int,
                "kept_entities": int,
                "quarantined_entities": int,
                "removed_entities": int
            }
        },
        ...
    ]
}
```

**Consumed by Phase 2 as:** `extraction_result["entities"]` (main.py line 108)

---

*End of Section 01.*
*All line numbers verified against direct code reading.*
