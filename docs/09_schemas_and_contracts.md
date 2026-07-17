# SECTION 09 — SCHEMAS AND DATA CONTRACTS
# CAD_ENGINE Design Authority Document

---

## 9.1 PURPOSE

This section documents every Pydantic schema and data contract used as inter-phase
boundaries in the CAD_ENGINE pipeline.

Schemas serve two purposes:
1. Runtime validation — data that fails schema validation raises an error at the boundary
2. Documentation contract — the schema is the machine-verified specification of what
   each phase produces and what the next phase consumes

---

## 9.2 GEOMETRY SCHEMA (schemas/geometry_schema.py)

**Full file path:** `schemas/geometry_schema.py` (79 lines)

### BaseEntity (line 9-19)

Base class for all normalized DXF entities. All entity schemas inherit this.

```python
class BaseEntity(BaseModel):
    source_file: str
    entity_type: str
    handle: str          # DXF internal entity handle (unique per file)
    layer: str           # Normalized layer name (uppercased)
    linetype: Optional[str] = None
    color: Optional[int] = None
```

### Typed Entity Schemas (lines 22-42)

| Class | Fields | Notes |
|-------|--------|-------|
| `LineEntity(BaseEntity)` | `start: Tuple[float, float]`, `end: Tuple[float, float]` | — |
| `CircleEntity(BaseEntity)` | `center: Tuple[float, float]`, `radius: float` | — |
| `ArcEntity(BaseEntity)` | `center`, `radius`, `start_angle: float`, `end_angle: float` | angles in degrees |
| `PolylineEntity(BaseEntity)` | `points: List[Tuple[float, float]]`, `closed: bool = False` | — |

**NOTE:** These typed entity schemas are the FORMAL specification. The actual pipeline
passes entities as `Dict[str, Any]` (untyped) for flexibility. The typed schemas serve
as the canonical reference for what the geometry dict MUST contain.

### RawDXFEntity (line 44-50)

```python
class RawDXFEntity(BaseModel):
    metadata: BaseEntity
    geometry: Dict[str, Any]
```

Wrapper for any DXF entity combining its metadata fields with its geometry dict.

---

## 9.3 FILTER PIPELINE SCHEMAS (schemas/geometry_schema.py, lines 56-79)

These schemas define the data contract for the filter chain output.

### FilteredEntity (line 57-60)

```python
class FilteredEntity(BaseModel):
    entity: Dict[str, Any]    # complete entity dictionary
    reason: str               # string explaining WHY it was filtered
    confidence: float = 0.5   # default 0.5 when confidence not computable
```

### EntityConfidence (line 62-66)

```python
class EntityConfidence(BaseModel):
    possible_overlap: bool = False
    overlap_confidence: float = 0.0
```

These two fields are mutated directly on the entity dict by DuplicateFilter:
```python
entity["possible_overlap"] = True
entity["overlap_confidence"] = 1.0
```

### FilterStatistics (line 68-72)

```python
class FilterStatistics(BaseModel):
    input_entities: int
    kept_entities: int
    quarantined_entities: int
    removed_entities: int
```

### FilterResult (line 75-79)

```python
class FilterResult(BaseModel):
    kept_entities: List[Dict[str, Any]]        # entities that passed all checks
    quarantined_entities: List[FilteredEntity]  # preserved but excluded
    removed_entities: List[FilteredEntity]      # permanently discarded
    statistics: FilterStatistics
```

This is the complete output of EVERY filter class (TextFilter, DegenerateFilter,
DuplicateFilter, LayerFilter, BorderFilter).

---

## 9.4 SEMANTIC SCHEMAS (pipeline/semantic_pipeline.py)

### FeatureInstance (line 53-65)

```python
@dataclass
class FeatureInstance:
    feature_id: str
    feature_class: str
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]: ...
```

### Relationship (line 68-82)

```python
@dataclass
class Relationship:
    relationship_id: str
    relationship_type: str
    feature_ids: List[str]
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]: ...
```

### SemanticRecord (line 86-108)

```python
@dataclass
class SemanticRecord:
    drawing_id: str
    part_type: str
    overall_dimensions: Dict[str, float]   # {"width": float, "height": float}
    features: List[FeatureInstance]
    relationships: List[Relationship]
    hierarchy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]: ...
```

---

## 9.5 EXPORTED SAMPLE CONTRACT (dataset_pipeline.py, lines 2000-2130)

The final JSONL export format is a strict schema enforced by the
validation stages in `_validate_structure()` and `_validate_schema()`.

### Allowed Root Keys (line 2103)

```python
allowed_root_keys = {
    "drawing_id", "context", "target",
    "system", "user", "assistant"
}
```

Any unexpected root key causes a **CRITICAL** Stage 2 rejection.

### Allowed Context Keys (line 2117)

```python
allowed_ctx_keys = {
    "drawing_id", "part_family", "manufacturing_type",
    "overall_dimensions", "inquiry_feature",
    "neighbour_features", "relationships", "topology"
}
```

Any unexpected context key causes a **CRITICAL** Stage 2 rejection.

### Target Structure

```python
{
    "property": str,   # e.g., "hole_diameter", "thread_size"
    "value": Any       # float or string depending on property type
}
```

### System/User/Assistant

The exported JSONL record contains:
- `"system"`: static engineering expert role description
- `"user"`: rendered natural language engineering question (with visible context)
- `"assistant"`: the target value as a string

---

## 9.6 SCHEMA VERSION CONSTANTS (dataset_pipeline.py, lines 1908-1912)

```python
VALIDATION_VERSION = "1.0.0"
DATASET_CONTRACT_VERSION = "3.0.0"
SCHEMA_VERSION = "2.1.0"
PROMPT_RENDERER_VERSION = "2.7.3"
PIPELINE_VERSION = "2.7.4"
```

All version constants are class-level attributes of `DatasetExporter`.
They are embedded in every `metadata.json` output file.

---

*End of Section 09.*
*All class names and field types verified against direct code reading.*
