# SECTION 12 — DESIGN DECISIONS AND ENGINEERING AUDIT
# CAD_ENGINE Design Authority Document

---

## 12.1 PURPOSE

This section documents every major architectural and algorithmic design decision
in the CAD_ENGINE pipeline. For each decision:
1. The DECISION is stated precisely
2. The RATIONALE is given (engineering justification)
3. The ALTERNATIVE is described
4. The TRADEOFF is acknowledged
5. Known LIMITATIONS are recorded honestly

This section is written to be defensible to a Principal Engineer who will
challenge every design choice.

---

## DECISION 1: Quarantine vs Delete for Degenerate Entities

**Decision:** DegenerateFilter defaults to `quarantine` rather than `remove`.
Only geometrically impossible values (negative length/radius) are permanently removed.
Tiny geometry (length ≤ 1e-6) is preserved in `quarantined_entities`.

**Rationale:**
Real engineering DXF files often contain intentional near-zero geometry.
A "tiny arc" may be a cosmetic fillet. A "tiny line" may be a precision datum line.
By quarantining rather than deleting, the pipeline preserves diagnostic information
and allows future recovery without re-parsing the DXF.

**Alternative:**
Delete all degenerate geometry. Simpler, smaller memory footprint, no quarantine bookkeeping.

**Tradeoff:**
Quarantine accumulates memory. For very large drawings with many degenerate entities,
the quarantine list may grow significantly. No per-run clearing mechanism exists.

**Limitation:**
Quarantined entities are currently not used downstream. The quarantine is effectively
a "preserve for future use" store. This value is not realised in the current codebase.
The current quarantine is documented ambition, not current capability.

---

## DECISION 2: Topology Built Purely from Shared Vertices

**Decision:** The topology graph is built exclusively from shared endpoint coordinates.
No distance heuristics, no visual proximity, no layer-based inference.

**Rationale:**
Distance-based "near connection" heuristics introduce false positives.
In a drawing with 200 entities, a 0.5mm proximity threshold might link entities
that are intentionally separate (adjacent holes, nearby features).
By requiring exact (snapped) coordinate sharing, the topology graph represents
only what the drafter explicitly connected.

**Alternative:**
Use Euclidean proximity with a configurable snap distance.
This would capture "almost connected" geometry that exists in lower-quality DXF exports.

**Tradeoff:**
Drawings exported from non-CAD software may have endpoint gaps of 0.01-0.5mm.
These drawings will have fragmented topology (many orphan entities) using the
current approach. The `VERTEX_PRECISION = 4` (0.1 micrometer) threshold is aggressive.

**Limitation:**
No topology repair / gap-closing mechanism exists. A drawing with 0.05mm endpoint
gaps will be fully disconnected. This is the single biggest limitation for
industrial DXF files from older CAD systems.

---

## DECISION 3: CIRCLE Entities Excluded from Topology

**Decision:** CIRCLE entities have no topology endpoints. They never participate
in the adjacency graph. `VertexIndexer._extract_endpoints()` explicitly
returns `[]` for CIRCLEs (line 106-107).

**Rationale:**
A mathematical circle is a closed curve with no endpoints. It cannot be
"connected" to a line in the graph-theoretic sense used by this pipeline.
CIRCLE-based holes in engineering drawings are represented by isolated circles
that appear at a position within a larger structural context.

**Alternative:**
Add CIRCLE quadrant points (0°, 90°, 180°, 270°) to topology for tangent detection.
Or: compute tangency with adjacent LINEs and ARCs to infer connections.

**Tradeoff:**
All CIRCLEs become topology orphans. A drawing with a bolt circle of 6 holes
(6 CIRCLEs) will have all 6 as orphan entities. The only mechanism connecting them
is the `ConcentricGrouping` (sharing center, not topology edge).
The `RadialPatternDetector` recognises bolt circles, but this does not
contribute to the topology graph.

**Evidence from production data:**
From the production metadata: 562 accepted samples include `with_concentric_evidence`
and `with_topology_evidence` as separate metadata flags — confirming that concentric
groups and topology are tracked independently.

---

## DECISION 4: Concentric Detection Uses Separate Precision from Topology

**Decision:** `ConcentricGrouping` uses `CENTER_PRECISION = 4` (line 25 of
concentric_grouping.py) — the same value as `VERTEX_PRECISION`. However,
these are independently applied to DIFFERENT coordinate types:
- `VERTEX_PRECISION`: applied to endpoint coordinates (line/arc endpoints)
- `CENTER_PRECISION`: applied to circle/arc center coordinates

**Rationale:**
Circle centers in a manufacturing drawing are expected to be exactly collocated
when features are concentric. A counterbore's two circles share exactly the same
center. If they don't match at 4 decimal places, they are likely NOT concentric.

**Alternative:**
Use a looser tolerance (e.g., precision=2, i.e., 0.01mm). This would group
"approximately concentric" circles that may have small center offsets due to
manufacturing or export rounding.

**Tradeoff:**
Tighter tolerance = fewer false concentric groups but may miss true concentricities
in imprecise DXF files.

---

## DECISION 5: Target Masking at the Dimension Type + Value Level

**Decision:** InferenceConditioner masks a target by removing from `other_own`
any dimension where BOTH `dimension_type == target_dim_type` AND
`abs(value - target_value) < 1e-6`. (line 159-165)

**Rationale:**
This precise mask ensures only the SPECIFIC target value is hidden.
If an entity has both `radius=5.0` and `diameter=10.0` and the target is `radius=5.0`,
the diameter is NOT masked — the model can still see it as reasoning evidence.

**Alternative:**
Mask all dimensions of an entity when that entity's dimension is targeted.
Simpler to implement but throws away valid evidence (e.g., hiding diameter
when only radius is the target).

**Tradeoff:**
The current approach is more precise but requires careful implementation.
The `1e-6` float tolerance is appropriate for computed dimensions but
could miss targets from imprecise DXF text parsing (e.g., a dimension of 9.9999
vs 10.0000).

**Known issue (from validation_report.json Stage 5 failures):**
In 4 cases, the target value STILL appeared in the rendered prompt text.
This means the masking at the context level was correct, but the prompt renderer
included the target value via a different path (visible_parameters of the inquiry feature).
This is a prompt rendering bug, not a masking logic bug.

---

## DECISION 6: Thread Size as a Discrete String Target

**Decision:** The `infer_thread_size` task accepts string targets like `"M8"`, `"G1/2"`,
`"NPT1/4"` rather than numeric values.

**Rationale:**
Thread designations are categorical engineering identifiers, not continuous numeric values.
`"M8"` means metric 8mm nominal diameter, 1.25mm pitch. It is NOT the number `8.0`.
A model that predicts `"8.0"` for a thread size has produced a wrong answer,
even if numerically it is close.

**Alternative:**
Decompose thread designation into numeric components (nominal diameter, pitch separately).
This would enable numeric evaluation but loses the engineering semantics of standard
thread designations.

**Tradeoff:**
String targets cannot be evaluated with MAE (mean absolute error).
The pipeline must use exact-match or fuzzy-match evaluation for thread size tasks.

---

## DECISION 7: No Semantic Disambiguation of Ambiguous Candidates

**Decision:** `CandidateConflictResolver` and `StructuralAmbiguityTracker` DETECT
conflicts and ambiguities but do NOT resolve them. The model receives conflicting
interpretations as context.

**Rationale:**
Forced disambiguation by geometric heuristics would introduce deterministic errors
that are difficult to audit. Preserving ambiguity allows the model to learn
the correct resolution from the training distribution.
In practice, most conflicts are between a slot candidate and a hole candidate
for the same elongated geometry — the model can resolve this using aspect ratio.

**Alternative:**
Apply priority rules: if a slot and hole candidate conflict, prefer slot
(higher aspect ratio evidence). This would produce cleaner training data
but might introduce systematic errors for non-standard geometry.

**Tradeoff:**
Ambiguous training samples increase noise. If the model sees the same geometry
with conflicting labels in different training examples, it will average them,
reducing prediction confidence for ambiguous features.

---

## DECISION 8: Bounding Box Containment for Contour Hierarchy

**Decision:** `ContourHierarchy.analyze()` uses bounding box containment as
a proxy for true polygon containment. (line 111-116 of contour_hierarchy.py)

**Rationale:**
True polygon containment (point-in-polygon testing) is O(n*m) where n is contour
vertices and m is the number of candidate parent contours. For large drawings
with many polylines, this is prohibitively slow.
Bounding box containment is O(1) per pair and eliminates most false positives.

**Alternative:**
Full polygon containment (even/odd ray casting). Correct for complex shapes.

**Tradeoff:**
Bounding box containment fails for L-shaped or non-convex outer profiles.
An L-shaped outer profile has a bounding box that extends over regions not
actually inside the part. Inner features in the "concave" region of the L
may be incorrectly classified as "inner" contours.

**Limitation:** This is the primary source of hierarchy errors for non-rectangular parts.

---

## DECISION 9: The Semantic Pipeline is Inside DatasetExporter

**Decision:** `SemanticPipeline` is a class within `dataset_pipeline.py` rather than
a separate pipeline phase.

**Rationale:**
The semantic pipeline operates on the complete multi-phase result dictionary.
It is not a sequential phase that produces an output consumed by the next phase.
It is a parallel transformation that builds named feature records alongside the
dataset sample generation. Keeping it within DatasetExporter reduces coupling.

**Alternative:**
Make semantic analysis a separate Phase 8 pipeline step, producing a separate output.
This would be cleaner architecturally but requires passing 137-drawing data through
an additional pipeline stage with associated memory and I/O overhead.

---

## DECISION 10: Deterministic (Not Random) Train/Val/Test Split

**Decision:** The split method is called `_split_deterministic()` in the source
comment (line 413), though the implementation uses sequential index-based splitting
rather than hash-based splitting.

**Rationale:**
Deterministic splits ensure reproducibility. The same set of drawings always
produces the same train/val/test distribution. This is critical for fair
comparison of model iterations trained on the same data.

**Alternative:**
Random split with fixed seed. Same reproducibility, but drawing order no longer matters.
Hash-based split by drawing_id. Ensures the same drawing never spans splits,
regardless of processing order.

**Known gap:**
There is no guarantee that drawings do not span splits in the current implementation.
If a single drawing generates 5 tasks, those 5 tasks may be distributed across
train, validation, and test — creating a data leakage risk where the same drawing
context appears in both training and evaluation.

---

## DECISION 11: Version Constants Embedded in Export Metadata

**Decision:** `VALIDATION_VERSION`, `DATASET_CONTRACT_VERSION`, `SCHEMA_VERSION`,
`PROMPT_RENDERER_VERSION`, `PIPELINE_VERSION` are class-level constants in `DatasetExporter`.
All are embedded in every exported `metadata.json`.

**Rationale:**
Every dataset artifact must be traceable to the exact code version that produced it.
If a model produces unexpectedly bad results, the first diagnostic question is
"which version of the pipeline generated this dataset?"

**Current versions (2026-07-06 production run):**
```
VALIDATION_VERSION = "1.0.0"
DATASET_CONTRACT_VERSION = "3.0.0"
SCHEMA_VERSION = "2.1.0"
PROMPT_RENDERER_VERSION = "2.7.3"
PIPELINE_VERSION = "2.7.4"
```

The large version numbers (3.0.0 for contract, 2.7.x for prompt/pipeline)
indicate substantial prior development and iteration before this code state.

---

## 12.2 KNOWN LIMITATIONS SUMMARY

| Area | Limitation | Severity |
|------|-----------|---------|
| Topology | No endpoint gap-closing; drawings with gaps >0.0001 units are fragmented | HIGH |
| CIRCLE topology | CIRCLEs are always topology orphans | MEDIUM |
| Contour hierarchy | Bounding-box containment fails for non-rectangular parts | MEDIUM |
| Config sync | `thresholds.yaml` values differ from hardcoded module constants | LOW |
| BLOCK/INSERT | `explode_inserts: true` in config but not implemented | LOW |
| Drawing split | No guarantee drawings don't span train/val/test | MEDIUM |
| Thread tasks | 8/8 thread-size rejections are systematic, not random | HIGH |
| Leakage | 4 cases of prompt-level leakage not caught by context masking | HIGH |
| `unknown_facts` | 106/469 features (22.6%) are unclassified engineering content | MEDIUM |

---

## 12.3 STRENGTHS SUMMARY

| Strength | Evidence |
|----------|---------|
| Deterministic pipeline | All outputs are reproducible from the same DXF input |
| Conservative quarantine policy | No engineering data permanently discarded without reason |
| Multi-level leakage prevention | Context masking + prompt validation catch two independent leakage vectors |
| Rich structural context | 5 distinct evidence signals (topology, repetition, concentric, feature, hierarchy) |
| Production-grade validation | 7-stage validation with per-sample rejection logging |
| Full traceability | Every rejected sample logged with stage, rule, severity, and recommendation |
| Thread type normalisation | Handles metric (M8), NPT, BSP/BSPP, G-series thread notations |
| Ambiguity preservation | Genuine geometric ambiguities are tracked and preserved in training data |

---

*End of Section 12.*
*All decisions grounded in direct code inspection. All limitations based on algorithmic analysis of verified implementation.*
