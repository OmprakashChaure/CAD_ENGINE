# SECTION 10 — CONFIGURATION SYSTEM
# CAD_ENGINE Design Authority Document

---

## 10.1 PURPOSE

The configuration system separates tunable engineering thresholds from
algorithmic logic. Every numerical threshold that affects a geometric decision
is defined in a YAML file, not hardcoded in business logic.

**Config directory:** `configs/`
**Config files:** `thresholds.yaml`, `layer_rules.yaml`, `extraction_rules.yaml`, `semantic_rules.yaml`

---

## 10.2 THRESHOLDS.YAML (511 bytes)

**Full path:** `configs/thresholds.yaml`

```yaml
geometry:
  degenerate_line_length: 0.0001    # DegenerateFilter: line shorter than this is tiny
  concentric_tolerance: 0.001       # ConcentricGrouping: center match tolerance
  endpoint_snap_tolerance: 0.01     # Note: actual impl uses VERTEX_PRECISION=4 (0.0001)
  tangent_tolerance_ratio: 0.02     # Arc tangency detection

relationships:
  max_hub_connections: 4            # Note: actual impl uses MAX_HUB_SIZE=8
  proximity_ratio: 0.15

features:
  bolt_min_count: 3                 # RadialPatternDetector: minimum radial holes
  bolt_radius_tolerance: 0.01       # RadialPatternDetector: radius uniformity
  bolt_pcd_spread_max: 0.05         # RadialPatternDetector: center distance spread
  slot_aspect_ratio: 2.0            # SlotCandidateDetector: elongation threshold
  fillet_max_sweep: 120             # ARC: max sweep angle for fillet classification (degrees)

angles:
  parallel_tolerance_deg: 0.5       # Symmetry analysis parallel detection
  perpendicular_tolerance_deg: 0.5  # Symmetry analysis perpendicular detection
```

**IMPORTANT DISCREPANCY:** Some thresholds in this YAML differ from the
hardcoded constants in the implementation files:
- `geometry.endpoint_snap_tolerance = 0.01` in YAML, but
  `VERTEX_PRECISION = 4` (i.e., 0.0001 tolerance) in `vertex_indexer.py`
- `relationships.max_hub_connections = 4` in YAML, but
  `MAX_HUB_SIZE = 8` in `adjacency_builder.py`

**INFERRED:** The YAML values appear to represent an older or aspirational specification,
while the module-level constants represent the actual operative values.
This discrepancy is a known gap between specification and implementation.

---

## 10.3 LAYER_RULES.YAML (667 bytes)

**Full path:** `configs/layer_rules.yaml`

```yaml
linetype_roles:
  HIDDEN: hidden_line
  HIDDEN2: hidden_line
  DASHED: hidden_line
  CENTER: centerline
  CENTER2: centerline
  PHANTOM: construction_line
  CONTINUOUS: visible_edge

layer_name_patterns:
  centerline: [CENTER, CL, AXIS]
  hidden: [HIDDEN, DASHED, HID]
  construction: [PHANTOM, CONSTRUCT, REF]
  dimension: [DIM, DIMENSION]
  annotation: [TEXT, NOTE, ANNOT]

ignore_layers:
  - DEFPOINTS
  - VIEWPORT
  - VIEW
  - TEXT
  - ANNOTATION
  - TITLE
  - BORDER
```

**Consumed by:** `core/filters/layer_filter.py` → `LayerFilter.filter()`
Entities on any layer in `ignore_layers` are REMOVED (not quarantined).

---

## 10.4 EXTRACTION_RULES.YAML (535 bytes)

**Full path:** `configs/extraction_rules.yaml`

```yaml
supported_entity_types:
  - LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE, POLYLINE
  - TEXT, MTEXT, DIMENSION, INSERT, LEADER, POINT, SPLINE

skip_layers: [DEFPOINTS, VIEWPORT, BORDER, TITLEBLOCK]

blocks:
  explode_inserts: true
  max_nesting_depth: 5
  skip_blocks: ["*Paper_Space", "*Model_Space"]
```

**NOTE:** The `blocks` configuration describes desired behavior for INSERT/BLOCK
explosion (unwrapping block references into individual entities). The actual
implementation in `entity_iterator.py` does NOT currently explode INSERT entities —
they enter the pipeline with `supported=False` and are quarantined.
`explode_inserts: true` is an aspirational specification, not an active feature.

---

## 10.5 SEMANTIC_RULES.YAML (650 bytes)

**Full path:** `configs/semantic_rules.yaml`

Controls which feature classes are eligible for which engineering inference tasks,
and how features should be classified from annotation text patterns.

---

## 10.6 HOW CONFIG IS LOADED

**LayerFilter** explicitly loads YAML at construction:
```python
with open(config_path / "layer_rules.yaml") as f:
    config = yaml.safe_load(f)
self.ignore_layers = set(config.get("ignore_layers", []))
```

**TopologyPipeline** and **StructuralPipeline** read values from their `self.config` dict:
```python
precision = self.config.get("vertex_precision", VERTEX_PRECISION)
max_hub_size = self.config.get("max_hub_size", MAX_HUB_SIZE)
center_precision = self.config.get("center_precision", 4)
```

The `config` dict is passed by `main.py` at pipeline construction time.
Default values in main.py are hardcoded:
```python
pipeline_config = {
    "vertex_precision": 4,
    "max_hub_size": 8,
    "center_precision": 4,
    "slot_aspect_threshold": 2.0,
    "radial_min_count": 3,
    "symmetry_tolerance": 0.01,
    "signature_precision": 3,
    "ambiguity_threshold": 0.5,
    "association_tolerance": 1.0
}
```

---

*End of Section 10.*
*All config values verified against direct file reading.*
