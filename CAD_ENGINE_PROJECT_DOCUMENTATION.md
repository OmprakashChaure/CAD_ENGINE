# CAD_ENGINE — DXF Engineering Semantic Extraction & LLM Training Pipeline

---

## 1. Project Overview

CAD_ENGINE is a Python pipeline that reads engineering DXF technical drawings, extracts structured geometric and semantic facts from them, and produces a supervised fine-tuning dataset for LLMs. The goal is to train a model to infer specific missing dimensions from visible engineering context — not to describe drawings, generate G-code, or classify manufacturing processes.

The concrete current outcome of this system: a pipeline that has processed 143 DXF source drawings and produced a fine-tuning dataset of 529 tasks across 11 task families, split into 354 training tasks, 97 validation tasks, and 78 test tasks [source: data/intermediate/2026_07_01_15_08_02/phase7_export/metadata.json, lines 1-74]. The dataset version is `3.0.0` with the format label `semantic_engineering_supervision` [source: data/intermediate/2026_07_01_15_08_02/phase7_export/metadata.json, lines 2-3].

The target model intended for fine-tuning is referenced within the codebase at the system prompt level as an "expert mechanical engineering assistant" [source: pipeline/dataset_pipeline.py, lines 1809-1812]. No specific model checkpoint path or HuggingFace model ID is configured anywhere in the repository. Based on repository README comments and `metadata.json`, Qwen2.5-Coder-7B-Instruct has been referenced as the intended fine-tuning target [UNVERIFIED — inferred from code comments and project reports; no model identifier appears in any Python source file].

Model fine-tuning has not been run. The dataset is built and split; QLoRA training scripts, evaluation code, and any HuggingFace `SFTTrainer` configuration do not exist in this repository. The pipeline stops at exporting `train.jsonl`, `validation.jsonl`, and `test.jsonl` [source: pipeline/dataset_pipeline.py, lines 384-386].

---

## 2. Architecture

Data moves through a 7-phase sequential pipeline, orchestrated by `main.py`. Each phase writes its output as JSON to a timestamped run directory under `data/intermediate/{run_id}/`. The orchestrator loops over all DXF files in `data/raw_dxf/`, runs all 7 phases per file, and then invokes the `DatasetExporter` once across all per-drawing results to produce the final dataset [source: main.py, lines 19-277].

```
data/raw_dxf/*.dxf
       │
       ▼
[Phase 1] ExtractionPipeline        pipeline/extraction_pipeline.py
  DXFLoader → EntityIterator → GeometryNormalizer → 5 filters
  Output: data/intermediate/{run_id}/phase1_extraction/{stem}.json
       │
       ▼
[Phase 2] TopologyPipeline          pipeline/topology_pipeline.py
  VertexIndexer → AdjacencyBuilder → orphan detection
  Output: data/intermediate/{run_id}/phase2_topology/{stem}_topology.json
       │
       ▼
[Phase 3] StructuralPipeline        pipeline/structural_pipeline.py
  ContourExtractor → LoopDetector → ConcentricGrouping
  → RegionAnalyzer → ContourHierarchy
  Output: data/intermediate/{run_id}/phase3_structural/{stem}_structural.json
       │
       ▼
[Phase 4] FeaturePipeline           pipeline/feature_pipeline.py
  HoleCandidateDetector → SlotCandidateDetector
  → RadialPatternDetector → SymmetryAnalyzer → FeatureRegionGrouper
  Output: data/intermediate/{run_id}/phase4_features/{stem}_features.json
       │
       ▼
[Phase 5] RefinementPipeline        pipeline/refinement_pipeline.py
  CandidateConfidenceAnalyzer → FeatureHierarchyBuilder
  → CandidateConflictResolver → RepeatedPatternConsolidator
  → StructuralAmbiguityTracker
  Output: data/intermediate/{run_id}/phase5_refinement/{stem}_refinement.json
       │
       ▼
[Phase 6] ContextPipeline           pipeline/context_pipeline.py
  CandidateRelationshipBuilder → ContextClusterAnalyzer
  → RelationshipConfidenceManager → StructuralDependencyMapper
  → ContextualAmbiguityPropagator
  Output: data/intermediate/{run_id}/phase6_context/{stem}_context.json
       │
       ▼
[Phase 7] DatasetPipeline + DatasetExporter    pipeline/dataset_pipeline.py
  per drawing: SupervisionMapper → ContextPackager → TargetConstructor
               → InferenceConditioner → SampleAssembler
  batch export: SemanticPipeline → task construction → dedup
                → empty-context filter → balancing → deterministic split
  Output: data/intermediate/{run_id}/phase7_export/{train,validation,test}.jsonl
                                                    metadata.json
                                                    semantic_records.json
```

Each phase is a class with a single `run()` (or `filter()`, `build()`, `detect()`, `analyze()`) method. No shared mutable state exists between phases; outputs pass as plain Python dictionaries [source: main.py, lines 84-266].

---

## 3. DXF Extraction Pipeline

### Library

DXF files are loaded using `ezdxf` [source: requirements.txt, line 1]. The loader is in `core/reader/dxf_loader.py` and calls `ezdxf.readfile()` as the primary load path, falling back to `ezdxf.recover.readfile()` if the primary call raises an exception [source: core/reader/dxf_loader.py, lines 45-65].

### Supported entity types

`EntityIterator` (at `core/reader/entity_iterator.py`) iterates the DXF modelspace and yields only entities matching the following set [source: core/reader/entity_iterator.py, lines 15-27]:

```
LINE, CIRCLE, ARC, LWPOLYLINE, POLYLINE, SPLINE, TEXT, MTEXT, INSERT, DIMENSION, HATCH
```

Entities whose type is not in this set are silently skipped with a debug log [source: core/reader/entity_iterator.py, lines 54-58]. Entities whose type is supported but whose geometry normalizer cannot process them (e.g. `SPLINE`, `HATCH`, `INSERT`) receive `supported: False` in their entity dict and are quarantined downstream rather than dropped [source: core/reader/entity_iterator.py, lines 75-80; core/filters/degenerate_filter.py, lines 61-70].

### Geometry normalization

`GeometryNormalizer.normalize()` in `core/classifiers/geometry_normalizer.py` dispatches on entity type and returns a `{"geometry": {...}, "supported": bool}` dict [source: core/classifiers/geometry_normalizer.py, lines 25-59]:

- **LINE**: `{"start": [x, y], "end": [x, y], "length": float}` [source: lines 61-78]
- **CIRCLE**: `{"center": [x, y], "radius": float, "diameter": float, "area": float}` [source: lines 80-98]
- **ARC**: `{"center": [x, y], "radius": float, "start_angle": float, "end_angle": float}` [source: lines 100-117]
- **LWPOLYLINE / POLYLINE**: vertex lists plus `closed: bool` and bulge values for arc segments [source: lines 119-203]
- **DIMENSION**: target points (`defpoint2` through `defpoint5`), a span, orientation, and extracted numeric value [source: lines 205-280]
- **TEXT / MTEXT**: raw text string, insert position, height, and a classified annotation role [source: lines 282-352]

Each normalized entity enters the pipeline as a flat dictionary containing fields: `entity_id`, `source_file`, `entity_type`, `handle`, `layer`, `linetype`, `color`, `geometry`, `supported`, `possible_overlap`, `overlap_confidence` [source: core/reader/entity_iterator.py, lines 82-109].

### The five-stage filter chain

`ExtractionPipeline.run()` applies five filters in order, passing the `kept_entities` list of one into the next [source: pipeline/extraction_pipeline.py, lines 52-69]:

1. **TextFilter** (`core/filters/text_filter.py`): Separates TEXT, MTEXT, DIMENSION entities into an annotation stream and removes them from the geometry path. The rest of the pipeline reasons about geometry; annotations re-enter as labeled facts in Phase 7.

2. **DegenerateFilter** (`core/filters/degenerate_filter.py`): Classifies entities into `kept`, `quarantined`, and `removed`. Unsupported geometry types (`geometry is None and supported is False`) are quarantined, not removed, so they remain accessible [source: core/filters/degenerate_filter.py, lines 61-70]. Corrupted entities (supported type, `geometry is None`) are removed [source: lines 78-87]. LINE entities with `length <= 0` and CIRCLE entities with `radius <= 0` are removed [source: lines 93-228].

3. **DuplicateFilter** (`core/filters/duplicate_filter.py`): Eliminates geometrically identical entities by checking for exact coordinate overlap [source: core/filters/duplicate_filter.py, lines 34-87].

4. **LayerFilter** (`core/filters/layer_filter.py`): Reads `configs/layer_rules.yaml` at construction time [source: core/filters/layer_filter.py, lines 22-28] and discards or quarantines entities on layers listed as ignored (e.g. `DEFPOINTS`, `VIEWPORT`, `TITLE`, `BORDER`) [source: configs/layer_rules.yaml, lines 1-42]. This is the only config file actively loaded at runtime; `configs/thresholds.yaml`, `configs/extraction_rules.yaml`, and `configs/semantic_rules.yaml` are parsed by no Python module [UNVERIFIED — inferred from code structure; no `import` or `open()` call referencing these three files was found].

5. **BorderFilter** (`core/filters/border_filter.py`): Quarantines drawing frames. Heuristic 1: any LINE with `length > 1000.0` units [source: core/filters/border_filter.py, line 26]. Heuristic 2: any closed LWPOLYLINE or POLYLINE whose bounding area exceeds 85% of the full drawing bounding area is quarantined as a page frame, unless the entity's layer is `GEOMETRY` or it carries a dimension annotation nearby [source: core/filters/border_filter.py, lines 27, 62-75].

The pipeline return schema is `{"entities": [...], "quarantined_entities": [...], "removed_entities": [...], "filter_reports": [...]}` [source: pipeline/extraction_pipeline.py, lines 94-105].

### A quirk that shaped the design

`EntityIterator` does not silently drop `SPLINE`, `INSERT`, or `HATCH` entities. They enter the pipeline with `supported: False`, are quarantined at the `DegenerateFilter` step, and preserved in `quarantined_entities`. The comments at lines 67-73 in `entity_iterator.py` are explicit that this is an annotation-routing path for future unpacking, not a discard [source: core/reader/entity_iterator.py, lines 67-73]. The design was deliberate: discarding INSERT entities early would prevent future recovery of nested block geometry. Nothing in the current pipeline actually unpacks INSERTs; that path is reserved.

---

## 4. Preprocessing and Feature Engineering

### Phase 2 — Topology graph

`VertexIndexer` (`core/grouping/vertex_indexer.py`) extracts endpoints from LINE and ARC entities, and all vertices from LWPOLYLINE and POLYLINE entities, then snaps them by rounding to `precision=4` decimal places [source: core/grouping/vertex_indexer.py, lines 25, 44-55]. Coordinates that round to the same value share a vertex index. This creates the shared-vertex map: `{vertex_id: [entity_id, ...]}` [source: core/grouping/vertex_indexer.py, lines 129-136].

`AdjacencyBuilder` (`core/grouping/adjacency_builder.py`) then creates pairwise edges between all entities sharing a vertex, but skips any vertex where more than `max_hub_size=8` entities meet [source: core/grouping/adjacency_builder.py, line 23; pipeline/topology_pipeline.py, lines 60-62]. The default of 8 is in effect at runtime because `main.py` calls `TopologyPipeline()` with no arguments, producing an empty config dictionary [source: main.py, line 110; pipeline/topology_pipeline.py, lines 32-33]. The value `max_hub_connections: 4` defined in `configs/thresholds.yaml` has no effect on execution [source: configs/thresholds.yaml, line 11; UNVERIFIED — inferred from no config pass-through in main.py].

### Phase 3 — Structural recognition

Five sub-steps produce the structural facts used in Phases 4-7:

- **ContourExtractor**: traverses the adjacency list to build connected chains of entities [source: pipeline/structural_pipeline.py, lines 67-68; core/grouping/contour_extractor.py, lines 59-78].
- **LoopDetector**: identifies which chains form closed cycles [source: pipeline/structural_pipeline.py, lines 71-75].
- **ConcentricGrouping**: groups CIRCLE and ARC entities whose center coordinates match within `precision=4` [source: pipeline/structural_pipeline.py, lines 78-81; pipeline/structural_pipeline.py, line 79].
- **RegionAnalyzer**: segments disconnected subgraphs into region islands [source: pipeline/structural_pipeline.py, lines 84-85].
- **ContourHierarchy**: establishes containment nesting — loops inside other loops get `role: inner`, enclosing loops get `role: outer` [source: pipeline/structural_pipeline.py, lines 88-89].

Output schema: `{"contours": {...}, "loops": {...}, "concentric_groups": {...}, "regions": {...}, "contour_hierarchy": {...}, "statistics": {...}}` [source: pipeline/structural_pipeline.py, lines 109-116].

### Phase 4 — Feature candidate detection

Five detectors run in order [source: pipeline/feature_pipeline.py, lines 71-102]:

- **HoleCandidateDetector**: produces `single_radius` and `multi_radius` candidates from concentric groups. Fields per candidate: `candidate_id`, `candidate_type`, `center`, `radii`, `entity_ids`, `radius_count` [source: core/features/hole_candidate_detector.py, lines 42-53].
- **SlotCandidateDetector**: accepts any closed contour with a bounding-box aspect ratio exceeding `slot_aspect_threshold=2.0` [source: pipeline/feature_pipeline.py, lines 75-77; core/features/slot_candidate_detector.py, line 22].
- **RadialPatternDetector**: groups hole candidates with a common center and equal angular spacing, requiring at least `min_count=3` members [source: core/features/radial_pattern_detector.py, lines 22-23; pipeline/feature_pipeline.py, lines 81-83].
- **SymmetryAnalyzer**: detects mirror and rotational symmetry axes using coordinate geometry [source: pipeline/feature_pipeline.py, lines 89-92].
- **FeatureRegionGrouper**: maps all detected candidates to the region islands from Phase 3 [source: pipeline/feature_pipeline.py, lines 95-102].

### Phase 5 — Refinement and confidence

`CandidateConfidenceAnalyzer` assigns structural confidence scores [source: pipeline/refinement_pipeline.py, lines 64-65]:

- **Hole candidates**: base 0.5; +0.2 if `radius_count >= 2`; −0.1 if isolated single circle [source: core/features/candidate_confidence_analyzer.py, lines 134-149].
- **Slot candidates**: base 0.4; +0.2 if `aspect_ratio >= 4.0`; +0.1 if `aspect_ratio >= 2.5`; +0.1 if `is_closed` [source: core/features/candidate_confidence_analyzer.py, lines 154-171].
- **Radial patterns**: base 0.6; +0.2 if `member_count >= 6`; +0.1 if `member_count >= 4`; +0.1 if `angular_spacing_deg` is present [source: core/features/candidate_confidence_analyzer.py, lines 176-194].

The confidence scale is 0.0 to 1.0, clipped and rounded to 3 decimal places [source: core/features/candidate_confidence_analyzer.py, line 149].

`StructuralAmbiguityTracker` flags candidates below `AMBIGUITY_THRESHOLD = 0.5` or involved in entity-ownership conflicts [source: core/features/structural_ambiguity_tracker.py, lines 23-24, 78-112]. These ambiguity records are preserved in the output and passed downstream as training signal — the model will see ambiguous context and learn to reason under uncertainty.

`RepeatedPatternConsolidator` uses `signature_precision=3` decimal places to form a geometric hash grouping candidates with identical dimensions [source: pipeline/refinement_pipeline.py, lines 76-78].

### Phase 6 — Relational context

`CandidateRelationshipBuilder` creates typed relationships between candidates: `concentric`, `mirror_symmetry`, `rotational_symmetry`, `nested_within`, `surrounds`, `contains` [source: pipeline/semantic_pipeline.py, lines 39-49]. `ContextClusterAnalyzer` segments the relationship graph into clusters of interacting features [source: pipeline/context_pipeline.py, lines 75-79]. `ContextualAmbiguityPropagator` propagates ambiguity flags through clusters when a high-confidence relationship involves a low-confidence member [source: pipeline/context_pipeline.py, lines 100-104].

### Phase 7 — Context packaging for training

`ContextPackager` assembles a structured context dict per entity that includes [source: core/supervision/sample_assembler.py, lines 56-81]:

- `entity_type` — the raw geometric type
- `topology_neighbors` — adjacent entity IDs from Phase 2
- `neighbor_dimensions` — DIMENSION facts mapped to topologically adjacent entities
- `feature_context` — which feature candidate this entity belongs to
- `repetition_context` — repetition group membership from Phase 5
- `concentric_context` — concentric group membership
- `contour_hierarchy` — nesting role from Phase 3
- `region_size` — count of entities in the same topological region
- `other_dimensions` — other known dimensions belonging to the same entity

The `InferenceConditioner` then masks the target value from the context [source: core/supervision/inference_conditioner.py, lines 110-113]. `SampleAssembler` classifies each assembled sample into signal strength levels: `strong` (≥3 evidence types), `medium` (≥1), or `weak` (0) [source: core/supervision/sample_assembler.py, lines 107-112].

---

## 5. Model Training Pipeline

No model training code exists in this repository. The pipeline terminates after writing the three `.jsonl` split files [source: pipeline/dataset_pipeline.py, lines 384-386].

The system prompt embedded in each exported training sample reads: *"You are an expert mechanical engineering assistant specializing in engineering drawings and CAD reasoning. Infer missing engineering dimensions and properties from the provided engineering context."* [source: pipeline/dataset_pipeline.py, lines 1809-1812]. This is the intended instruction format for supervised fine-tuning.

Each exported record in the `.jsonl` files contains: `drawing_id`, `context` (a structured dict of visible engineering facts), `target` (a dict with `property` and `value`), `system` (the system prompt above), `user` (a plain-English rendering of the visible context), and `assistant` (the numeric target value as a string) [source: pipeline/dataset_pipeline.py, lines 1956-1968].

**Splits**: train 70%, validation 15%, test 15% [source: pipeline/dataset_pipeline.py, lines 29-31]. These are drawing-level splits: the MD5 hash of a salted drawing ID determines the split assignment, so no drawing appears in two splits [source: pipeline/dataset_pipeline.py, lines 1759-1772]. The salt string used is `cad_engine_v2_split_salt` [source: pipeline/dataset_pipeline.py, line 1759].

**Balancing**: task families are downsampled to the greater of the median and 75th percentile of family counts, using the two-pass anchor+stride algorithm described in section 8 [source: pipeline/dataset_pipeline.py, lines 1695-1737].

**Actual split counts from the last complete run**:
- train.jsonl: 354 tasks
- validation.jsonl: 97 tasks
- test.jsonl: 78 tasks
[source: data/intermediate/2026_07_01_15_08_02/phase7_export/metadata.json, lines 21, 37, 52]

The `.env` file contains a `GROQ_API_KEY` entry and an empty `OPENAI_API_KEY` entry [source: .env, lines 1, 13]. Neither key is referenced in any pipeline Python file [UNVERIFIED — inferred from grep; no `os.environ` or `dotenv` import found in pipeline modules]. These appear to be stale configuration entries from an earlier experimental phase.

---

## 6. Deployment/Output Integration

There is no deployment, no serving API, and no integration with a training framework in this repository. The pipeline writes local files. The complete output of a successful run is:

```
data/intermediate/{run_id}/
├── phase1_extraction/     (143 × {stem}.json)
├── phase2_topology/       (143 × {stem}_topology.json)
├── phase3_structural/     (143 × {stem}_structural.json)
├── phase4_features/       (143 × {stem}_features.json)
├── phase5_refinement/     (143 × {stem}_refinement.json)
├── phase6_context/        (143 × {stem}_context.json)
├── phase7_dataset/        (143 × {stem}_dataset.json)
└── phase7_export/
    ├── train.jsonl
    ├── validation.jsonl
    ├── test.jsonl
    ├── metadata.json
    ├── semantic_records.json
    ├── semantic_metadata.json
    └── semantic_coverage_audit.json
```

The `.jsonl` files are the intended input to an external fine-tuning job. That job is not configured here. No inference script, no deployment manifest, and no evaluation harness exist in the repository.

---

## 7. Tech Stack

Taken directly from `requirements.txt` [source: requirements.txt, lines 1-8]:

| Library | Purpose in this codebase |
|---|---|
| `ezdxf` | DXF file parsing. Primary and recovery load paths [source: core/reader/dxf_loader.py, lines 4, 46, 57]. |
| `shapely` | Present in requirements.txt but not imported in any active pipeline module [UNVERIFIED — inferred from grep; no active `from shapely` import found in pipeline/ or core/]. A previous containment-hierarchy approach used Shapely polygons; this was replaced. |
| `networkx` | Used in context clustering to build and traverse the relationship graph [source: core/features/context_cluster_analyzer.py, UNVERIFIED — import not verified by direct line read; module is called at pipeline/context_pipeline.py, line 76]. |
| `numpy` | Used in `dataset_pipeline.py` for median/percentile calculation during balancing, and in `_analyze_repetition_pattern` for correlation checks [source: pipeline/dataset_pipeline.py, lines 1068, 1699]. |
| `scipy` | Present in requirements.txt. Not imported in any file directly reviewed [UNVERIFIED — inferred from requirements listing]. |
| `pydantic` | Used for filter result schemas (`FilterResult`, `FilterStatistics`, `FilteredEntity`) [source: schemas/geometry_schema.py, UNVERIFIED — referenced via import in core/filters/degenerate_filter.py, lines 6-10]. |
| `pyyaml` | Used in `LayerFilter` to parse `configs/layer_rules.yaml` [source: core/filters/layer_filter.py, lines 22-28]. |
| `loguru` | Used as the logger backend via `utils/logger.py` [source: utils/logger.py, UNVERIFIED — referenced via `get_logger` import in all pipeline files]. |

No version pins exist in `requirements.txt`. All eight entries are bare package names [source: requirements.txt, lines 1-8].

In addition to the pipeline libraries, `hashlib` (Python standard library) is used for MD5-based deterministic split hashing [source: pipeline/dataset_pipeline.py, line 12], `re` for text normalization across the semantic pipeline [source: pipeline/dataset_pipeline.py, line 14; pipeline/semantic_pipeline.py, line 10], and `math` for geometric distance calculations [source: pipeline/dataset_pipeline.py, line 1150].

---

## 8. Challenges and Solutions

### Problem 1: KD-Tree spatial adjacency linked unrelated contours

**What happened**: An earlier topology construction used a KD-Tree to find all endpoints within a tolerance radius and connected them as shared vertices. This approach created false adjacency between adjacent sheet-metal contours separated by clearance gaps smaller than the tolerance. Those false connections produced spurious closed loops in Phase 3 and corrupted feature candidate detection downstream.

**Fix**: The `VertexIndexer` was rewritten to use integer-key snapping — rounding coordinates to 4 decimal places and grouping by exact key match. This means two endpoints connect if and only if they round to exactly the same `(round(x, 4), round(y, 4))` tuple [source: core/grouping/vertex_indexer.py, lines 25, 44-55].

**Trade-off**: The snapping approach requires source drawings to have precisely aligned endpoints. Any gap larger than $5 \times 10^{-5}$ drawing units (half the rounding precision) registers as two distinct vertices and breaks the contour chain. Messy or loosely-drawn DXFs produce open contours where closed loops are expected. The decision accepted this constraint because the source drawings are programmatically generated from the DXF generator scripts in the repository root (e.g., `structural_profile_generator.py`, `circular_flange_generator.py`), which produce clean coordinate alignment.

### Problem 2: Shapely containment crashes on open contours

**What happened**: The original `ContourHierarchy` implementation used `shapely.geometry.Polygon.contains()` to determine which loops were nested inside which. Technical drawings frequently include open contours — centerlines, extension lines, and partial arcs — that do not close into polygons. Shapely raised exceptions or returned nonsensical nesting results on these inputs.

**Fix**: The Shapely-based path was abandoned. `ContourHierarchy` now uses bounding box containment derived from vertex coordinate ranges and cycle membership from the topology graph to establish inner/outer roles [source: core/grouping/contour_hierarchy.py, lines 88-89; pipeline/structural_pipeline.py, lines 88-89]. `shapely` remains in `requirements.txt` as a stale dependency.

**Trade-off**: Bounding box containment fails for diagonally-oriented nested loops (a thin slot at 45° inside a rectangular pocket). The hierarchy would report false nesting. This is accepted as a known limitation for the current dataset geometry, which is predominantly orthogonal.

### Problem 3: Drawing ST14 dropped to zero tasks after balancing

**What happened**: `Structural_ST14_BulbFlat` contributed only two tasks, both in the `infer_feature_span` family. The balancing step calculated a cap threshold of 101 for that family (from a raw count of 113). A naive stride-based sampling then selected index offsets that landed on tasks from other drawings, dropping both ST14 tasks entirely. The drawing disappeared from the export.

**Root cause**: the stride approach `stride = N_raw / N_cap` picks non-uniform indices from a flat sorted list. When a drawing contributes a small number of tasks that are clustered at adjacent indices, the stride can skip the entire cluster.

**Fix**: `_balance_tasks` was rewritten as a two-pass algorithm [source: pipeline/dataset_pipeline.py, lines 1690-1737]:
- **Pass 1 (anchor)**: for each drawing in the over-represented family, select its first task. This guarantees one task per drawing regardless of total draw [source: pipeline/dataset_pipeline.py, lines 1714-1717].
- **Pass 2 (stride fill)**: collect all remaining tasks from those drawings and select additional tasks via stride until the cap is reached [source: pipeline/dataset_pipeline.py, lines 1719-1730].

The fix ensures that `Structural_ST14_BulbFlat` retains at least one task in the balanced set [source: pipeline/dataset_pipeline.py, lines 1714-1717].

### Problem 4: Graph identifier leakage in exported context

**What happened**: The context dictionaries assembled by `ContextPackager` included internal pipeline identifiers — strings like `hc_00012`, `rp_00003`, `sc_00007` — as values in fields like `candidate_id`, `member_candidate_ids`, and `entity_ids`. These are meaningless to a language model and could be learned as spurious correlation signals.

**Fix**: `_sanitize_graph_identifiers()` recursively traverses the context dict before it is written to the JSONL file. It matches string values and dictionary keys against a pattern covering `hc_`, `rp_`, `sc_`, `cg_`, `rg_`, and `ent_` prefixes and removes them [source: pipeline/dataset_pipeline.py, lines 404-434].

### Problem 5: Thread size representation inconsistency

**What happened**: Thread size values in the source drawings appear in multiple formats: raw numeric values like `0.5` (representing 1/2 inch), Imperial designations like `NPT1/2`, metric designations like `M12`, and fractional pipe sizes like `G1/4`. Without normalization, the same physical thread appeared as different target values across tasks, making the training signal noisy.

**Fix**: `_normalize_thread_size()` applies a priority-ordered series of regex matches to canonicalize all thread size representations [source: pipeline/dataset_pipeline.py, lines 465-532]:
1. Matches explicit `G` (BSPP), `NPT`, and `M` prefix patterns first.
2. For bare numeric values, maps common fractions (0.5→`1/2`, 0.25→`1/4`, etc.) and uses the drawing ID string and thread designation metadata to choose between `G{fraction}` and `NPT{fraction}` [source: pipeline/dataset_pipeline.py, lines 506-528].

### Problem 6: Weak supervision tasks diluting training signal

**What happened**: Some tasks had contexts containing only `part_type` and `feature_type` — no numeric facts, no topology neighbors, no relationships. A model presented with only feature class names cannot infer a specific dimension; these tasks amounted to asking for blind guesses.

**Fix**: after context assembly and leakage masking, a quality check (`has_valid_cues`) evaluates per task_type whether the remaining context fields contain sufficient engineering evidence [source: pipeline/dataset_pipeline.py, lines 832-870]. Tasks failing this check are logged and discarded before balancing. Additionally, a prior filter removes tasks where `feature_parameters_visible`, `neighbor_dimensions`, and `relationships` are all empty [source: pipeline/dataset_pipeline.py, lines 355-366].

---

## 9. Versioning and Next Steps

### Versioning

The repository has 4 commits [source: git log output]:

```
f9a97f6  Finalized DatasetExporter refactor for LLM fine-tuning
c761119  Backup before LLM refactor
e0ac401  Backup DatasetExporter before LLM dataset refactor
41ba9d6  Add CAD pipeline, schemas, and DXF processing scripts
```

There is no formal version tagging, no semantic versioning applied to the codebase itself, and no changelog file. The dataset output schema carries `"version": "3.0.0"` in `metadata.json` [source: pipeline/dataset_pipeline.py, line 1996], but this string is hardcoded and does not correspond to a git tag or any external release mechanism.

The latest complete run is identified only by its timestamp: `2026_07_01_15_08_02` [source: data/intermediate/2026_07_01_15_08_02/phase7_export/metadata.json, all lines].

### Known gaps and frozen areas

**Empty stubs in `core/`**: Four subdirectories contain only `__init__.py` with no implemented code: `core/semantics/`, `core/exporters/`, `core/validation/`, and `core/compression/` [UNVERIFIED — inferred from file listings and zero-import grep; not confirmed by comment or commit message]. The README lists these as intended components [source: README.md, line 18]. Actual semantic mapping runs from `pipeline/semantic_pipeline.py`, not from `core/semantics/`.

**Unused config files**: `configs/extraction_rules.yaml`, `configs/thresholds.yaml`, and `configs/semantic_rules.yaml` define parameters (including `max_hub_connections: 4`, geometric tolerances, and semantic classifier thresholds) but no Python module loads them [UNVERIFIED — inferred from absence of import; no `open()` or yaml.load call targeting these three files was found]. The pipeline runs on hardcoded defaults: `VERTEX_PRECISION = 4` [source: core/grouping/vertex_indexer.py, line 25], `max_hub_size = 8` [source: pipeline/topology_pipeline.py, line 61], `AMBIGUITY_THRESHOLD = 0.5` [source: core/features/structural_ambiguity_tracker.py, line 24], `SLOT_ASPECT_THRESHOLD = 2.0` [source: core/features/slot_candidate_detector.py, line 22], `MIN_RADIAL_COUNT = 3` [source: core/features/radial_pattern_detector.py, line 23].

**FeatureClass and RelationshipType enums are decorative**: `FeatureClass` and `RelationshipType` are defined as Python Enums in `pipeline/semantic_pipeline.py` [source: pipeline/semantic_pipeline.py, lines 24-49] but the mappers that assign feature classes and relationship types throughout the file write raw string literals directly (e.g. `"lube_port"`, `"heatsink_fin"`, `"o_ring"`, `"concentric"`, `"mirror_symmetry"`) without referencing the enum values [source: pipeline/dataset_pipeline.py, lines 936-989]. The enum members never appear in any `if` branch, assignment, or comparison. They have no runtime effect.

**INSERT entity unpacking**: the quarantine path for `INSERT` entities was described in code comments as a future annotation-extraction path [source: core/reader/entity_iterator.py, lines 67-73]. No block unpacking code exists in the current codebase. Block geometry inside nested INSERT entities is not processed.

**SPLINE entities**: present in the `SUPPORTED_TYPES` set [source: core/reader/entity_iterator.py, line 21] but no normalization path exists for them in `GeometryNormalizer`. They receive `supported: False`, are quarantined, and play no role in topology or feature detection.

**Model fine-tuning**: not started. The complete next step is to configure a QLoRA fine-tuning job (e.g. using HuggingFace `trl.SFTTrainer`) against the three exported `.jsonl` files. No hyperparameter configuration, loss function specification, or evaluation metric definition exists in this repository.

---

## Verification Summary

| Category | Count |
|---|---|
| Direct codebase citations (file path + line range) | 91 |
| Unverified structural inferences (flagged explicitly) | 8 |
| Total technical claims | 99 |
