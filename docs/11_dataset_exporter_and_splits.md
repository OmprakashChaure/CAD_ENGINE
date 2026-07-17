# SECTION 11 — DATASET EXPORTER AND OUTPUT FORMAT
# CAD_ENGINE Design Authority Document

---

## 11.1 PURPOSE

This section documents the complete output format produced by DatasetExporter,
the train/val/test split strategy, the 7-stage validation pipeline applied to
each exported sample, and the auto-fix operations.

---

## 11.2 DATASET EXPORTER ARCHITECTURE

**Class:** `DatasetExporter` (pipeline/dataset_pipeline.py)
**Invoked by:** `main.py` line 256+

### Export Workflow (verified from DatasetExporter.export() implementation)

```
Step 1: Build SemanticRecords (per drawing)
          SemanticPipeline._build() → SemanticRecord per DXF
          + Validation: overall_dimensions cross-check
          + Validation: concentric bore sanity
          
Step 2: Export semantic_records.json
          JSON array of all SemanticRecord.to_dict()
          + semantic_metadata.json (feature/relationship distributions)
          
Step 3: Build engineering inference tasks from SemanticRecords
          _build_tasks_from_semantic() → task dict per property per feature
          
Step 4: Deduplicate tasks
          Signature: (drawing_id, json(context), json(target))
          
Step 5: Filter empty-context tasks
          Condition: has_params OR has_neighbors OR has_relations
          
Step 6: Balance tasks (_balance_tasks())
          
Step 7: Deterministic split
          _split_deterministic(all_tasks) → (train, val, test)
          
Step 8: Write JSONL with per-sample validation
          _write_jsonl() → applies validation + auto-fix + writes to file
          
Step 9: Write validation_report.json
          One record per rejected sample
          
Step 10: Generate semantic coverage audit
Step 11: Export metadata.json
```

---

## 11.3 TASK STRUCTURE

Each task dictionary has this structure before export:

```python
{
    "drawing_id": str,
    "task_type": str,          # e.g., "infer_hole_diameter"
    "context": {
        # allowed context keys (strict schema):
        "drawing_id": str,
        "part_family": str,
        "manufacturing_type": str,
        "overall_dimensions": {"width": float, "height": float},
        "inquiry_feature": {
            "feature_class": str,
            "visible_parameters": {key: value, ...}
        },
        "neighbour_features": [
            {"feature_class": str, "visible_parameters": {...}}
        ],
        "relationships": [
            {"type": str, "associated_features": [...], "parameters": {...}}
        ],
        "topology": {
            "contours": int, "nesting": int, "holes": int, "regions": int
        }
    },
    "target": {
        "property": str,    # dimension type
        "value": Any        # numeric or thread size string
    }
}
```

### Graph Identifier Sanitization (`_sanitize_graph_identifiers()`, line 466-496)

Before export, all internal pipeline IDs are stripped from the context:
```python
if k in ("candidate_id", "parent_id", "children_ids", "group_id",
         "relationship_id", "feature_id", "entity_id", "entity_ids",
         "member_candidate_ids", "candidate_ids"):
    continue  # strip field entirely
```
String values matching patterns like `hc_*`, `rp_*`, `sc_*`, `ent_*` etc. are
set to `None` or removed from lists.

**Engineering rationale:** Internal pipeline identifiers (`ent_00001`, `hc_00003`)
are meaningless to the model. Exposing them would create noise — the model should
not learn to reason based on arbitrary entity IDs.

---

## 11.4 TASK-SPECIFIC CONTEXT FILTERING (`_filter_context_by_task()`, line 2600-2622)

Applied during `_write_jsonl()` before prompt rendering.

| Task Type | Filtering Applied |
|-----------|-------------------|
| `infer_thread_size` | Removes `topology` key entirely |
| `infer_profile_dimension` | Removes `topology` key entirely |
| `infer_wall_thickness` | Retains only concentric/coaxial/nested relationships |
| All others | No filtering — full context passed |

**Engineering rationale:** Thread sizing does not depend on topological connectivity;
it depends on feature geometry and engineering relationships (coaxial, adjacent bore).
Removing irrelevant topology reduces noise in the input context.

---

## 11.5 PROMPT RENDERING (`_build_instruction_prompt()`, lines 1700-1906)

Renders each task into natural language engineering text.

**Prompt structure:**

```
[system]
You are an expert mechanical engineer...

[user]
Task: <task_type formatted>

Drawing Description:
Part Type: <part_type>
Overall Dimensions: <width> x <height> mm

The part contains:
<feature descriptions with visible parameters>

Adjacent features visible: <neighbour summary>

Relationships: <concentric/mirror/pattern relationships>

Topology: <contour counts, nesting depth, hole count, regions>

Question:
Based on the drawing layout and dimensions, infer the missing <property> in mm.

[assistant]
<target value as string>
```

### Mandatory Prompt Sections (checked in `_validate_prompt_quality()`, line 2380-2440)

The following sections MUST be present in the rendered user prompt:
- `"task:"` (case-insensitive)
- `"description:"` (case-insensitive)
- `"question:"` (case-insensitive)

Missing any of these causes a **MAJOR** Stage 6 rejection.

---

## 11.6 7-STAGE VALIDATION PIPELINE

Applied to every sample during `_write_jsonl()` before writing to disk.

| Stage | Method | Rule | Severity if Failed |
|-------|--------|------|-------------------|
| 1 | `_validate_structure()` | Mandatory root fields: drawing_id, context, target, system, user, assistant | CRITICAL |
| 2 | `_validate_schema()` | No unexpected root/context keys | CRITICAL |
| 3 | `_validate_reasoning()` | `infer_thread_size` requires overall_dims + geometry + relationships | CRITICAL |
| 4 | `_validate_reasoning()` | Any task must have at least one of: overall_dims, geometry, relationships, topology | MAJOR |
| 5 | `_validate_leakage()` | Target value must not appear in prompt text | CRITICAL |
| 6 | `_validate_prompt_quality()` | Prompt must contain task/description/question sections, length 50-4000 chars | MAJOR |
| 7 | `_validate_duplicates()` | No duplicate keys (pitch vs thread_pitch) or duplicate neighbours | MINOR |

**Auto-fix (`_autofix_sample()`, line 1914-1997):** Applied BEFORE validation, not after.
Fixes that do not require rejection:
- Removes duplicate `drawing_id` from context dict
- Deduplicates `neighbour_features` by (feature_class, parameters) signature
- Deduplicates `relationships` by (type, sorted features, parameters) signature
- Strips "null" and "none" rendering placeholders from prompt text
- Fixes snake_case feature names to Title Case
- Removes duplicate prompt lines
- Normalises multiple spaces and blank lines

---

## 11.7 PRODUCTION VALIDATION RESULTS

From `data/intermediate/2026_07_06_10_03_41/phase7_export/` (verified file read):

| Metric | Value |
|--------|-------|
| Total processed | 574 |
| Accepted | 562 |
| Rejected | 12 |
| Rejection rate | 2.09% |
| Average prompt length | 851.12 chars |
| Average context length (JSON) | 764.48 chars |
| Processing duration | 5.40 seconds |
| Source drawings | 109 |
| Semantic records built | 137 |

**Rejection breakdown (from validation_report.json, 134 lines, 12 records):**

| Failure | Stage | Rule | Count | Affected Drawings |
|---------|-------|------|-------|-------------------|
| Target value in prompt | Stage 5 | Target Leakage | 4 | Thermal_HS01, Gasket_GS02, SheetMetal_SM07, Weldment_WD05 |
| Missing engineering relationships | Stage 3 | Engineering Dataset Contract | 8 | Hardware_HW02 (×2), Hardware_HW03, Hardware_HW04 (×2), Fluid_PF02, Thermal_HS04, Turned_Shaft_TS01 |

**Root cause analysis of Stage 3 failures:**
All 8 failures are `infer_thread_size` tasks. The Stage 3 contract for thread size
requires `engineering relationships` to be present. Hardware fastener drawings (screws, bolts)
are isolated geometric objects — they typically have no concentric or mirror relationships
with surrounding features. This is a known systematic gap: thread-size-only fastener drawings
cannot satisfy the relationship contract without redesigning the task construction logic.

**Root cause analysis of Stage 5 failures:**
Target values appeared inside the rendered `user` prompt text, specifically in
feature parameter descriptions. The prompt renderer was including visible parameters
of the inquiry feature that happened to contain the target value.
Recommendation (from validation_report.json): "Update the prompt renderer to strip
annotation values for target features."

---

## 11.8 OUTPUT FILES PRODUCED

```
data/intermediate/<run_timestamp>/phase7_export/
├── train.jsonl              # 372 samples, ~750 KB
├── validation.jsonl         # 104 samples, ~200 KB
├── test.jsonl               # 86 samples, ~165 KB
├── semantic_records.json    # 137 SemanticRecord dicts, ~430 KB
├── semantic_metadata.json   # Feature/relationship distributions, ~835 bytes
├── metadata.json            # Run statistics, version constants, split counts
├── validation_report.json   # Per-rejection records
└── semantic_coverage_audit.json  # Coverage analysis, ~12.5 KB
```

---

## 11.9 JSONL FORMAT

Each line of train.jsonl/validation.jsonl/test.jsonl is a single JSON object:

```json
{
  "drawing_id": "Plate_BP01_FlangeBase",
  "context": {
    "part_family": "structural",
    "manufacturing_type": "machined",
    "overall_dimensions": {"width": 200.0, "height": 150.0},
    "inquiry_feature": {
      "feature_class": "concentric_bore",
      "visible_parameters": {"outer_diameter": 80.0, "center": [100.0, 75.0]}
    },
    "neighbour_features": [...],
    "relationships": [{"type": "concentric", ...}],
    "topology": {"contours": 3, "nesting": 1, "holes": 4, "regions": 1}
  },
  "target": {"property": "bore_diameter", "value": 50.0},
  "system": "You are an expert mechanical engineer...",
  "user": "Task: Infer Bore Diameter\n\nDrawing Description:\n...\nQuestion:\n...",
  "assistant": "50.0"
}
```

---

*End of Section 11.*
*All statistics verified from direct file reads of the production output directory.*
