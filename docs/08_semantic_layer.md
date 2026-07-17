# SECTION 08 — SEMANTIC LAYER
# CAD_ENGINE Design Authority Document

---

## 8.1 PURPOSE

The semantic layer sits inside DatasetExporter (pipeline/dataset_pipeline.py) and
transforms the structural analysis from Phases 1-6 into named engineering features
and engineering task records.

This is the boundary between geometric analysis and engineering meaning.

**File:** `pipeline/semantic_pipeline.py` (2194 lines, 89 KB)
**Invoked by:** `DatasetExporter.export()` → Step 1 (line 247)

---

## 8.2 DATA SCHEMAS (lines 25-108)

### FeatureClass Enum (line 25-37)

```python
class FeatureClass(Enum):
    HOLE_PATTERN = "hole_pattern"
    HOLE_GROUP = "hole_group"
    CONCENTRIC_BORE = "concentric_bore"
    SLOT_ARRAY = "slot_array"
    SLOT_GROUP = "slot_group"
    FILLET_GROUP = "fillet_group"
    CHAMFER_GROUP = "chamfer_group"
    OUTER_PROFILE = "outer_profile"
    RADIAL_PATTERN = "radial_pattern"
    LINEAR_PATTERN = "linear_pattern"
    MIRROR_PATTERN = "mirror_pattern"
```

### RelationshipType Enum (line 40-50)

```python
class RelationshipType(Enum):
    CONCENTRIC = "concentric"
    COAXIAL = "coaxial"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    MIRROR_SYMMETRY = "mirror_symmetry"
    ROTATIONAL_SYMMETRY = "rotational_symmetry"
    NESTED_WITHIN = "nested_within"
    SURROUNDS = "surrounds"
    CONTAINS = "contains"
```

### FeatureInstance (line 53-65)

```python
@dataclass
class FeatureInstance:
    feature_id: str
    feature_class: str
    parameters: Dict[str, Any]
```

### SemanticRecord (line 86-108)

The complete semantic representation of one drawing:
```python
@dataclass
class SemanticRecord:
    drawing_id: str
    part_type: str
    overall_dimensions: Dict[str, float]  # {"width": float, "height": float}
    features: List[FeatureInstance]
    relationships: List[Relationship]
    hierarchy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

---

## 8.3 ENGINEERING CONCEPT REGISTRY (lines 163-239)

**Class:** `EngineeringConcept` (line 140-160)

Each concept has:
- `name`: canonical concept name
- `synonyms`: list of text strings that match this concept
- `geometry_classes`: geometric detector results that confirm this concept
- `exclude_words`: text patterns that REJECT this concept even if synonyms match

### Matching Logic (line 147-160)

```python
def matches_text(self, text: str) -> bool:
    # 1. Exclude check first
    if any(_match_keyword(text_upper, ex) for ex in self.exclude_words):
        return False
    # 2. Synonym check
    return any(_match_keyword(text_upper, syn) for syn in self.synonyms)

def calculate_confidence(self, text: str, detected_geom_classes: List[str]) -> float:
    score = 0.0
    if self.matches_text(text): score += 2.0  # text match
    for gc in self.geometry_classes:
        if gc in detected_geom_classes: score += 1.5  # geometry corroboration
    return score
```

The `_match_keyword()` function uses word-boundary regex to prevent false matches:
`r'(?:^|[^A-Z0-9])' + escaped + r'(?:$|[^A-Z0-9])'`
This prevents "BORE" matching "ELBOW" or "BUTTON" matching "BUTTON_HEAD".

### Complete CONCEPT_REGISTRY (line 163-239)

| Registry Key | Feature Name | Synonyms (Partial) | Geometry Classes | Exclude Words |
|-------------|-------------|-------------------|------------------|---------------|
| THREAD | thread | THREAD, NPT, BSP, BSPT, UNC, UNF, TAP, M-SERIES | thread | PITCH CIRCLE, PCD |
| BORE | bore | BORE, THRU BORE, PRECISION BORE, ALIGNMENT BORE | concentric_bore | — |
| HOLE | hole | HOLE, CLEARANCE HOLE, MOUNTING HOLE, BOLT HOLE | hole_group, hole_pattern | — |
| POCKET | pocket | POCKET, MILLED POCKET, RECESS, OPENING | pocket | — |
| RIB | rib | RIB, RIBS, CRUSH RIBS, STIFFENER | rib | — |
| PORT | port | PORT, INLET, OUTLET, LUBE PORT | port | — |
| CHANNEL | channel | CHANNEL, FLOW CHANNEL, COOLING CHANNEL | channel | — |
| SHOULDER | shoulder | SHOULDER, STEP LENGTH, SHOULDER LEN | shoulder | — |
| COPE | cope | COPE, FISHMOUTH, TUBE COPE, SADDLE | cope | — |
| CHAMFER | chamfer | CHAMFER, BEVEL | chamfer | — |
| RELIEF | relief | RELIEF, BEND RELIEF, CORNER RELIEF | bend_relief | — |
| FIN | fin | FIN, FINS, COOLING FIN, RADIAL FIN | heatsink_fin | — |
| FLANGE | flange | FLANGE, FLANGE OD, FLANGE THK | fitting, structural_profile | — |
| WEB | web | WEB THK, WEB THICKNESS | structural_profile | — |
| O_RING | o_ring | O-RING, ORING, SEAL GROOVE | o_ring | — |

### SYNONYMS Dictionary (line 123-129)

Pre-defined synonym groups for reuse across concepts:
```python
SYNONYMS = {
    "THREAD": ["THREAD", "NPT", "BSP", "BSPT", "UNC", "UNF", "UNEF", "TAPPED", ...],
    "WEB_THICKNESS": ["WEB THK", "WEB THICKNESS", "WEB THICK", "WEAKENED WEB"],
    "FLANGE_THICKNESS": ["FLANGE THK", "FLANGE THICKNESS"],
    "ACROSS_FLATS": ["AF", "A/F", "ACROSS FLATS", "WIDTH ACROSS FLATS"],
    "BEND_RELIEF": ["RELIEF", "BEND RELIEF", "CORNER RELIEF", "HINGE RELIEF"]
}
```

---

## 8.4 TEXT PROCESSING UTILITIES (lines 243-320)

### `_clean_text()` (line 243-246)

```python
def _clean_text(text: Optional[str]) -> str:
    return text.replace("%%C", "Ø").replace("\\P", " ").replace("\\", " ").upper()
```

Handles DXF special codes: `%%C` is AutoCAD's diameter symbol code.

### `parse_fractional_value()` (line 249-260)

Handles imperial fraction format: `"1/2"`, `"3 1/4"`, `"\\S1/2;"` (DXF format):
```python
match = re.search(r"(?:(\d+)[- ])?(\d+)/(\d+)", text)
return whole + num / den
```

### `strip_count_prefix()` (line 263-265)

Removes patterns like `"4X "` from dimension text `"4X Ø8"`:
```python
cleaned = re.sub(r"^\s*\d+\s*[Xx]\s+", "", text)
```

### `_orientation()` (line 285-297)

Determines dimension line orientation from defpoints:
```python
if dx >= dy: return "horizontal"
return "vertical"
```

### `_physical_bbox()` (line 323-350)

Computes the drawing's physical bounding box from visible geometry,
explicitly EXCLUDING layers: `CENTERLINES, CONSTRUCTION, DATUM, REFERENCE, DIMENSIONS`.

This is used to determine `overall_dimensions` for the SemanticRecord.

---

## 8.5 VALIDATION PIPELINE (`SemanticPipeline._validate()`)

After building each SemanticRecord, it is validated before acceptance.
Invalid records are logged and skipped.

Additionally, DatasetExporter runs two cross-validation checks:
1. **Overall dimension sanity** (line 294-307): Compares `semantic_record.overall_dimensions`
   to the computed outer contour bounding box. If they differ by >5% in width or height,
   a warning is logged.
2. **Concentric bore sanity** (line 309-321): For any `concentric_bore` feature,
   verifies `bore_diameter < outer_diameter`. If violated, a warning is logged.

---

## 8.6 FEATURE CLASS DISTRIBUTION (from production run, semantic_metadata.json)

From the 2026-07-06 production pipeline run (137 drawings processed):

| Feature Class | Count |
|---------------|-------|
| unknown_facts | 106 |
| dimension_annotations | 104 |
| pocket | 55 |
| concentric_bore | 67 |
| hole_group | 34 |
| hole_pattern | 10 |
| structural_profile | 15 |
| thread | 12 |
| fitting | 6 |
| slot_array | 6 |
| bend_relief | 6 |
| rib | 5 |
| port | 5 |
| alignment_tab | 5 |
| hex_head | 5 |
| fillet_group | 4 |
| bolt | 3 |
| heatsink_core | 3 |
| heatsink_fin | 3 |
| keyway | 3 |
| cope | 2 |
| channel | 2 |
| sheet_metal_bend | 2 |
| shoulder | 2 |
| o_ring | 1 |
| lube_port | 1 |
| screw | 1 |
| hex_drive | 1 |

**NOTE:** `unknown_facts` (106) and `dimension_annotations` (104) are large categories.
These represent features that the semantic classifier extracted from drawing annotation text
but could not assign to a specific engineering feature class.
This is a known limitation and a subject for future engineering attention.

**Total features:** 469 across 137 drawings = 3.42 features per drawing on average.

**Relationship distribution:**
- `mirror_symmetry`: 81 relationships
- `concentric`: 62 relationships
- **Total relationships:** 143

---

## 8.7 ENGINEERING INFERENCE TASKS (from production metadata.json)

The DatasetExporter generates 11 task types from SemanticRecords.
From the 2026-07-06 production run (562 accepted tasks from 574 processed):

| Task Type | Total | Train | Validation | Test |
|-----------|-------|-------|------------|------|
| infer_pocket_dimension | 76 | 50 | 16 | 10 |
| infer_wall_thickness | 48 | 33 | 7 | 8 |
| infer_spacing | 72 | 50 | 13 | 9 |
| infer_hole_count | 47 | 31 | 10 | 6 |
| infer_hole_diameter | 45 | 30 | 8 | 7 |
| infer_bore_diameter | 60 | 39 | 11 | 10 |
| infer_outer_diameter | 31 | 25 | 3 | 3 |
| infer_slot_dimension | 22 | 14 | — | 8 |
| infer_feature_span | 76 | 49 | 17 | 10 |
| infer_profile_dimension | 73 | 44 | 18 | 11 |
| infer_thread_size | 12 | 7 | 1 | 4 |
| **TOTAL** | **562** | **372** | **104** | **86** |

**Split ratios (approximate):**
- Train: 372/562 = 66.2%
- Validation: 104/562 = 18.5%
- Test: 86/562 = 15.3%

**Rejection rate:** 12/574 = 2.09%
- Stage 3 (Engineering Dataset Contract) failures: 8 → all `infer_thread_size` tasks lacking engineering relationships
- Stage 5 (Target Leakage) failures: 4 → target value appeared in prompt text

---

*End of Section 08.*
*Production statistics verified from data/intermediate/2026_07_06_10_03_41/phase7_export/metadata.json and semantic_metadata.json.*
