# DESIGN AUTHORITY DOCUMENT (DAD)
# CAD_ENGINE — Deterministic DXF-to-LLM Engineering Dataset Pipeline
# Version 1.0 — Authored from direct source code inspection

---

## DOCUMENT PURPOSE

This document is the authoritative engineering reference for the CAD_ENGINE pipeline.

Every claim in every section is grounded in direct source code reading.
No function, class, or algorithm is described without citing the file and location where it was confirmed.
Where intent cannot be verified from code alone, the text is explicitly labelled **[INFERRED]**.

This document is written to be defensible before:
- AI/ML Engineers reviewing dataset construction methodology
- Mechanical Engineers reviewing CAD concept correctness
- Senior Software Engineers reviewing architecture and module boundaries
- Principal Engineers challenging any design decision

---

## DOCUMENT SECTIONS

| Section | File | Contents |
|---------|------|----------|
| 00 | 00_mechanical_to_code_bridge.md | Mechanical concept to code mapping matrix |
| 01 | 01_phase1_extraction.md | Phase 1: DXF loading, entity iteration, geometry normalization, filter chain |
| 02 | 02_phase2_topology.md | Phase 2: Vertex indexing, adjacency graph, orphan detection |
| 03 | 03_phase3_structural.md | Phase 3: Contour extraction, loop detection, concentric grouping, region analysis, hierarchy |
| 04 | 04_phase4_features.md | Phase 4: Hole candidates, slot candidates, radial patterns, symmetry analysis |
| 05 | 05_phase5_refinement.md | Phase 5: Confidence scoring, hierarchy building, conflict detection, repetition consolidation, ambiguity tracking |
| 06 | 06_phase6_context.md | Phase 6: Candidate relationships, context clusters, dependency mapping, ambiguity propagation |
| 07 | 07_phase7_dataset.md | Phase 7: Supervision mapping, context packaging, target construction, inference conditioning, sample assembly |
| 08 | 08_semantic_layer.md | Semantic pipeline: concept registry, feature classification, engineering value resolution |
| 09 | 09_schemas_and_contracts.md | Pydantic schemas, data contracts, inter-phase API surface |
| 10 | 10_configuration_system.md | YAML configuration files, threshold registry, layer rules |
| 11 | 11_dataset_exporter_and_splits.md | DatasetExporter, train/val/test split logic, JSONL output format |
| 12 | 12_design_decisions_and_audit.md | Engineering audit: every major architectural decision, rationale, and known limitations |

---

## PIPELINE OVERVIEW

DXF File
    |
    v
[Phase 1: Extraction]
  DXFLoader (ezdxf.recover.readfile)
  EntityIterator (modelspace)
  GeometryNormalizer
  Filter Chain: TextFilter -> DegenerateFilter -> DuplicateFilter -> LayerFilter -> BorderFilter
    |
    v kept_entities: List[Dict]
[Phase 2: Topology]
  VertexIndexer (coordinate snapping, precision=4)
  AdjacencyBuilder (shared-vertex connectivity, max_hub=8)
    |
    v adjacency_list, shared_vertices, edges
[Phase 3: Structural]
  ContourExtractor -> LoopDetector -> ConcentricGrouping -> RegionAnalyzer -> ContourHierarchy
    |
    v contours, loops, concentric_groups, regions, hierarchy
[Phase 4: Features]
  HoleCandidateDetector -> SlotCandidateDetector -> RadialPatternDetector -> SymmetryAnalyzer
    |
    v hole_candidates, slot_candidates, radial_patterns, symmetry
[Phase 5: Refinement]
  ConfidenceAnalyzer -> HierarchyBuilder -> ConflictResolver -> PatternConsolidator -> AmbiguityTracker
    |
    v confidence, hierarchy, conflicts, repetitions, ambiguity
[Phase 6: Context]
  RelationshipBuilder -> ClusterAnalyzer -> ConfidenceManager -> DependencyMapper -> AmbiguityPropagator
    |
    v relationships, clusters, dependencies, ambiguity_propagation
[Phase 7: Dataset]
  SupervisionMapper -> ContextPackager -> TargetConstructor -> InferenceConditioner -> SampleAssembler
    |
    v training_samples (JSONL)
[DatasetExporter]
  SemanticPipeline + Train/Val/Test split (70/15/15)

---

*All sections produced from direct source code inspection.*
