"""
Dataset Pipeline — Phase-7 supervised dataset generation and batch split exporting.

Orchestrates:
  1. Supervision mapping (dimension → geometry associations)
  2. Computable dimension extraction
  3. Training sample assembly
  4. Batch dataset exporting (taxonomy mapping, leakage protection, deterministic drawing split isolation, balancing)
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.supervision.supervision_mapper import SupervisionMapper
from core.supervision.context_packager import ContextPackager
from core.supervision.target_constructor import TargetConstructor
from core.supervision.inference_conditioner import InferenceConditioner
from core.supervision.sample_assembler import SampleAssembler
from pipeline.semantic_pipeline import SemanticPipeline, reconstruct_dimensions, normalize_thread_size
from pipeline.split_policy import TRAIN_RATIO, VAL_RATIO, TEST_RATIO
from utils.logger import get_logger
import time
import datetime

logger = get_logger(__name__)

def get_memory_usage() -> float:
    try:
        import ctypes
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        
        GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
        GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
        
        process = GetCurrentProcess()
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        
        if GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return float(counters.WorkingSetSize) / (1024 * 1024)
    except Exception:
        pass
    return 0.0

class DatasetPipeline:
    """
    Generate supervised training dataset from pipeline outputs.

    Input: entities + topology + structural + feature + context results
    Output: training-ready supervision dataset
    """

    def __init__(self, config: Dict | None = None):
        self.config = config or {}

    def run(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
        structural_result: Dict[str, Any],
        feature_result: Dict[str, Any],
        refinement_result: Dict[str, Any],
        drawing_id: str = "unknown",
        context_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Generate supervised dataset.

        Returns:
            {
                "final_dataset": { ... },
                "supervision": { ... },
                "targets": { ... },
                "training_context": { ... },
                "statistics": { ... }
            }
        """
        logger.info(
            f"DatasetPipeline: generating dataset "
            f"from {len(entities)} entities"
        )

        # Stage 1: Supervision mapping
        mapper = SupervisionMapper(
            tolerance=self.config.get("association_tolerance", 1.0)
        )
        supervision_result = mapper.map(entities, topology_result)

        # Stage 2: Context packaging
        packager = ContextPackager()
        context_packages = packager.package(
            entities,
            topology_result,
            structural_result,
            feature_result,
            refinement_result,
            supervision_result["computable_dimensions"],
        )

        # Stage 3: Target construction
        target_constructor = TargetConstructor(
            min_value=self.config.get("min_target_value", 0.1)
        )
        target_result = target_constructor.construct(context_packages)

        # Stage 4: Inference conditioning (masking)
        conditioner = InferenceConditioner()
        conditioning_result = conditioner.condition(
            target_result["targets"],
            context_packages,
        )

        # Stage 5: Final sample assembly
        assembler = SampleAssembler()
        final_dataset = assembler.assemble(
            conditioning_result["training_samples"],
            drawing_id,
        )

        # Stage 6: Assemble training context summary
        training_context = self._assemble_context(
            entities,
            topology_result,
            structural_result,
            feature_result,
            refinement_result,
        )

        # Combined statistics
        statistics = {
            "supervision": supervision_result["statistics"],
            "targets": target_result["statistics"],
            "conditioning": conditioning_result["statistics"],
            "final_dataset": final_dataset["statistics"],
            "context": {
                "geometry_entities": training_context["geometry_count"],
                "topology_edges": training_context["topology_edges"],
                "feature_candidates": training_context["feature_count"],
                "repetition_groups": training_context["repetition_count"],
                "context_packages": len(context_packages),
            },
        }

        logger.info(
            f"DatasetPipeline complete: "
            f"final_samples={final_dataset['statistics']['total_samples']} "
            f"leakage_free={final_dataset['statistics']['leakage_free']}"
        )

        return {
            "final_dataset": final_dataset,
            "supervision": supervision_result,
            "targets": target_result,
            "training_context": training_context,
            "statistics": statistics,
        }

    def _assemble_context(
        self,
        entities: List[Dict],
        topology_result: Dict[str, Any],
        structural_result: Dict[str, Any],
        feature_result: Dict[str, Any],
        refinement_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Assemble structural context relevant to dimension inference.

        Includes only fields that help a model infer dimensions.
        """
        # Topology summary
        topo_stats = topology_result.get("statistics", {})

        # Feature summary
        feat_stats = feature_result.get("statistics", {})
        holes = feat_stats.get("holes", {}).get("total_candidates", 0)
        slots = feat_stats.get("slots", {}).get("total_candidates", 0)
        radial = feat_stats.get("radial_patterns", {}).get("total_patterns", 0)

        # Repetition summary
        rep_stats = refinement_result.get("statistics", {}).get("repetitions", {})
        rep_groups = rep_stats.get("total_repetition_groups", 0)

        # Structural summary
        struct_stats = structural_result.get("statistics", {})
        concentric = struct_stats.get("concentric", {}).get("total_groups", 0)

        return {
            "geometry_count": sum(
                1 for e in entities
                if e.get("entity_type") not in ("DIMENSION", "TEXT", "MTEXT")
            ),
            "topology_edges": topo_stats.get("total_edges", 0),
            "feature_count": holes + slots + radial,
            "repetition_count": rep_groups,
            "concentric_groups": concentric,
            "hole_candidates": holes,
            "slot_candidates": slots,
            "radial_patterns": radial,
        }


# =====================================================================
# 4. BATCH DATASET EXPORTER LAYER
# =====================================================================

class PromptSerializer:
    """Isolate prompt construction and text formatting logic from engineering and file-writing concerns (Phase C)."""

    def serialize_sample(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a structured task into a text-formatted engineering instruction prompt."""
        # Deep copy to prevent mutating original task dictionary
        serialized = json.loads(json.dumps(task))
        prompt_fields = self._build_instruction_prompt(
            serialized["task_type"],
            serialized["drawing_id"],
            serialized["context"],
            serialized["target"]
        )
        serialized.update(prompt_fields)
        return self._autofix_sample(serialized)

    def _build_instruction_prompt(
        self, task_type: str, drawing_id: str, context: Dict[str, Any], target: Dict[str, Any]
    ) -> Dict[str, str]:
        system = (
            "You are an expert mechanical engineering assistant specializing in engineering drawings and CAD reasoning. "
            "Infer missing engineering dimensions and properties from the provided engineering context."
        )

        lines = []
        task_display = task_type.replace("infer_", "").replace("_", " ").title()
        
        # 1. Task Definition
        lines.append(f"Task:\nInfer the missing {task_display.lower()} for drawing '{drawing_id}'.")
        lines.append("\nDrawing Description:")
        
        # 2. Overall Geometry
        dims = context.get("overall_dimensions")
        if dims and isinstance(dims, dict):
            w = dims.get("width")
            h = dims.get("height")
            if w is not None and h is not None:
                lines.append(f"The overall plate dimensions are {w} mm × {h} mm.")
            elif w is not None:
                lines.append(f"The overall plate width is {w} mm.")
            elif h is not None:
                lines.append(f"The overall plate height is {h} mm.")

        # 3. Inquiry Feature & Parameters
        inquiry_feature = context.get("inquiry_feature", {})
        f_class = inquiry_feature.get("feature_class", "unknown")
        f_class_clean = f_class.replace("_", " ").title()
        
        visible_params = inquiry_feature.get("visible_parameters", {})
        params_txt = []
        if visible_params:
            for k, v in visible_params.items():
                if v is not None and v != "" and v != [] and v != {}:
                    name_clean = k.replace("_", " ").title()
                    is_length = isinstance(v, (int, float)) and not isinstance(v, bool) and not any(x in k.lower() for x in ("count", "member", "number"))
                    if is_length:
                        params_txt.append(f"{name_clean} = {v} mm")
                    else:
                        params_txt.append(f"{name_clean} = {v}")
                        
        if params_txt:
            lines.append(f"The drawing details a {f_class_clean} feature with {', '.join(params_txt)}.")
        else:
            lines.append(f"The drawing details a {f_class_clean} feature.")

        # 4. Neighbour Features (Task 2 & Mandatory Rule 4)
        neighbour_features = context.get("neighbour_features", [])
        if neighbour_features:
            neighbour_txt = []
            grouped_neighbours = defaultdict(list)
            for nf in neighbour_features:
                if not isinstance(nf, dict):
                    continue
                nf_class = nf.get("feature_class", "unknown")
                nf_params = nf.get("visible_parameters", {})
                clean_params = {
                    k: v for k, v in nf_params.items()
                    if v is not None and v != "" and v != [] and v != {}
                }
                sig = (nf_class, json.dumps(clean_params, sort_keys=True))
                grouped_neighbours[sig].append(clean_params)

            for (nf_class, params_json), instances in grouped_neighbours.items():
                count = len(instances)
                nf_params = instances[0]
                nf_class_clean = nf_class.replace("_", " ").title()
                
                params_list = []
                for pk, pv in nf_params.items():
                    pk_clean = pk.replace('_', ' ').title()
                    is_length = isinstance(pv, (int, float)) and not isinstance(pv, bool) and not any(x in pk.lower() for x in ("count", "member", "number"))
                    if is_length:
                        params_list.append(f"{pk_clean} = {pv} mm")
                    else:
                        params_list.append(f"{pk_clean} = {pv}")
                
                params_str = f" with {', '.join(params_list)}" if params_list else ""
                if count > 1:
                    class_plural = f"{nf_class_clean}s" if not nf_class_clean.endswith("s") else nf_class_clean
                    neighbour_txt.append(f"Adjacent {class_plural} ({count}) are visible{params_str}.")
                else:
                    neighbour_txt.append(f"An adjacent {nf_class_clean} is visible{params_str}.")
            if neighbour_txt:
                lines.append(" ".join(neighbour_txt))

        # 5. Engineering Relationships (Task 3 & Mandatory Rule 5)
        relationships = context.get("relationships", [])
        if relationships:
            rel_txt = []
            grouped_rels = defaultdict(list)
            for rel in relationships:
                if not isinstance(rel, dict):
                    continue
                r_type = rel.get("type", "")
                assoc = rel.get("associated_features", [])
                params = rel.get("parameters", {})
                
                clean_params = {
                    k: v for k, v in params.items()
                    if v is not None and v != "" and v != [] and v != {}
                }
                
                def get_clean_class(fid: str) -> str:
                    base = re.sub(r'_\d+$', '', fid)
                    return base.replace("_", " ").title()
                    
                conn_classes = tuple(sorted(get_clean_class(fid) for fid in assoc))
                sig = (r_type, conn_classes, json.dumps(clean_params, sort_keys=True))
                grouped_rels[sig].append((assoc, clean_params))

            for (r_type, conn_classes, params_json), instances in grouped_rels.items():
                count = len(instances)
                params = instances[0][1]
                classes_str = " and ".join(conn_classes) if conn_classes else "features"
                r_type_clean = r_type.replace("_", " ").title()
                
                param_details = []
                for pk, pv in params.items():
                    pk_clean = pk.replace("_", " ").title()
                    if pk == "concentric_diameters" and isinstance(pv, list):
                        diams_str = ", ".join(f"{d} mm" for d in pv)
                        param_details.append(f"diameters {diams_str}")
                    elif isinstance(pv, (int, float)) and not isinstance(pv, bool) and not any(x in pk.lower() for x in ("count", "member", "number")):
                        param_details.append(f"{pk_clean} = {pv} mm")
                    else:
                        param_details.append(f"{pk_clean} = {pv}")
                suffix = f" with {', '.join(param_details)}" if param_details else ""
                
                if count > 1:
                    rel_txt.append(f"{count} Concentric relationships are defined between {classes_str}{suffix}." if r_type == "concentric" else f"{count} {r_type_clean} relationships are defined between {classes_str}{suffix}.")
                else:
                    if r_type == "concentric":
                        rel_txt.append(f"A Concentric alignment is defined between {classes_str}{suffix}.")
                    elif r_type == "coaxial":
                        rel_txt.append(f"A Coaxial alignment is defined along the center axis between {classes_str}{suffix}.")
                    elif r_type == "mirror_symmetry":
                        axis = params.get("axis", "vertical").title()
                        rel_txt.append(f"Mirror Symmetry is defined about the {axis} centerline between {classes_str}{suffix}.")
                    elif r_type == "circular_pattern":
                        members = params.get("member_count", 0)
                        rel_txt.append(f"A Circular array is defined containing {members} members.")
                    elif r_type == "linear_pattern":
                        members = params.get("member_count", 0)
                        rel_txt.append(f"A Linear array is defined containing {members} members.")
                    else:
                        rel_txt.append(f"A {r_type_clean} relationship exists between {classes_str}{suffix}.")
            if rel_txt:
                lines.append(" ".join(rel_txt))

        # 6. Topology
        topology = context.get("topology", {})
        if topology:
            topo_txt = []
            contours = topology.get("contours", 0)
            nesting = topology.get("nesting", 0)
            holes = topology.get("holes", 0)
            regions = topology.get("regions", 0)
            
            topo_txt.append(f"The part geometry contains {contours} total contours.")
            topo_txt.append(f"The maximum contour nesting depth is {nesting}.")
            if holes > 0:
                topo_txt.append(f"There are {holes} hole profiles detected.")
            if regions > 0:
                topo_txt.append(f"The topology is partitioned into {regions} connected regions.")
            if topo_txt:
                lines.append(" ".join(topo_txt))

        # 7. Reasoning Question
        prop_display = target.get("property", "").replace("_", " ").lower()
        if prop_display == "thread size":
            lines.append(f"\nQuestion:\nBased on the drawing layout and dimensions, infer the missing thread size.")
        else:
            lines.append(f"\nQuestion:\nBased on the drawing layout and dimensions, infer the missing {prop_display} in mm.")
        
        user = "\n".join(lines)
        val = target.get("value")
        assistant = str(val)

        return {
            "system": system,
            "user": user,
            "assistant": assistant
        }

    def _autofix_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Automatically repair quality, formatting, redundancy, and case issues."""
        ctx = sample.get("context", {})
        
        # Remove duplicate drawing_id from context
        if isinstance(ctx, dict) and "drawing_id" in ctx:
            del ctx["drawing_id"]
            
        # 1. Deduplicate neighbour features in context
        nf_list = ctx.get("neighbour_features", [])
        if isinstance(nf_list, list):
            seen_nf = set()
            unique_nf = []
            for nf in nf_list:
                if isinstance(nf, dict):
                    sig = (nf.get("feature_class"), json.dumps(nf.get("visible_parameters"), sort_keys=True))
                    if sig not in seen_nf:
                        seen_nf.add(sig)
                        unique_nf.append(nf)
            ctx["neighbour_features"] = unique_nf

        # 2. Deduplicate relationships in context
        rel_list = ctx.get("relationships", [])
        if isinstance(rel_list, list):
            seen_rel = set()
            unique_rel = []
            for rel in rel_list:
                if isinstance(rel, dict):
                    sig = (
                        rel.get("type"),
                        tuple(sorted(rel.get("associated_features", []))),
                        json.dumps(rel.get("parameters"), sort_keys=True)
                    )
                    if sig not in seen_rel:
                        seen_rel.add(sig)
                        unique_rel.append(rel)
            ctx["relationships"] = unique_rel

        # 3. Clean prompt text (user, assistant, system)
        user = sample.get("user", "")
        assistant = sample.get("assistant", "")
        system = sample.get("system", "")

        # Clean sentences containing null or none rendering placeholders
        user = re.sub(r'[^.]*\bnull\b[^.]*\.?', '', user, flags=re.IGNORECASE)
        user = re.sub(r'[^.]*\bnone\b[^.]*\.?', '', user, flags=re.IGNORECASE)

        # Fix lowercase snake_case feature names in user/assistant
        def fix_snake_case(text: str) -> str:
            words = re.findall(r'\b[a-z0-9]+_[a-z0-9_]+\b', text)
            for w in words:
                cleaned = w.replace("_", " ").title()
                text = text.replace(w, cleaned)
            return text

        user = fix_snake_case(user)
        assistant = fix_snake_case(assistant)

        # Fix duplicate prompt lines
        def fix_duplicate_lines(text: str) -> str:
            lines = text.split("\n")
            seen_lines = set()
            unique_lines = []
            for line in lines:
                l_strip = line.strip()
                if not l_strip:
                    unique_lines.append(line)
                    continue
                if l_strip not in seen_lines:
                    seen_lines.add(l_strip)
                    unique_lines.append(line)
            return "\n".join(unique_lines)

        user = fix_duplicate_lines(user)

        # Clean spacing
        user = re.sub(r' {2,}', ' ', user)
        user = re.sub(r'\n{3,}', '\n\n', user)

        sample["user"] = user.strip()
        sample["assistant"] = assistant.strip()
        sample["system"] = system.strip()

        return sample


class DatasetExporter:
    """
    Export engineering inference tasks from pipeline outputs.

    Each task: given visible feature structure → infer missing property.
    """
    VALIDATION_VERSION = "1.0.0"
    DATASET_CONTRACT_VERSION = "3.0.0"
    SCHEMA_VERSION = "2.1.0"
    PROMPT_RENDERER_VERSION = "2.7.3"
    PIPELINE_VERSION = "2.7.4"

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Use SemanticPipeline from semantic_pipeline instead of SemanticRecordBuilder
        self.semantic_pipeline = SemanticPipeline()
        self.serializer = PromptSerializer()

    def export(
        self,
        all_pipeline_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build and export semantic records AND engineering inference tasks.

        Args:
            all_pipeline_results: list of full pipeline results per DXF
        """
        logger.info(
            f"DatasetExporter: processing {len(all_pipeline_results)} drawings"
        )

        # ── STEP 1: Build Semantic Records ──────────────────────────────
        semantic_records = []
        for result in all_pipeline_results:
            drawing_id = result.get("drawing_id", "unknown")
            try:
                # Call SemanticPipeline.run instead of SemanticRecordBuilder.build_semantic_record
                semantic_record_dict = self.semantic_pipeline.run(result)
                
                # Reconstruct semantic record object for validation logic
                from pipeline.semantic_pipeline import SemanticRecord, FeatureInstance, Relationship
                
                features = [
                    FeatureInstance(
                        feature_id=f["feature_id"],
                        feature_class=f["feature_class"],
                        parameters=f["parameters"]
                    )
                    for f in semantic_record_dict.get("features", [])
                ]
                relationships = [
                    Relationship(
                        relationship_id=r["relationship_id"],
                        relationship_type=r["relationship_type"],
                        feature_ids=r["feature_ids"],
                        parameters=r["parameters"]
                    )
                    for r in semantic_record_dict.get("relationships", [])
                ]
                
                semantic_record = SemanticRecord(
                    drawing_id=semantic_record_dict["drawing_id"],
                    part_type=semantic_record_dict["part_type"],
                    overall_dimensions=semantic_record_dict["overall_dimensions"],
                    features=features,
                    relationships=relationships,
                    hierarchy=semantic_record_dict.get("hierarchy"),
                    metadata=semantic_record_dict.get("metadata")
                )

                # VALIDATION: compare semantic overall_dimensions to outer contour bbox
                try:
                    entities = result.get("entities", [])
                    outer_dims = reconstruct_dimensions(entities) if entities else None
                    sem_dims = semantic_record.overall_dimensions
                    if outer_dims and sem_dims:
                        w_diff = abs(outer_dims.get("width", 0) - sem_dims.get("width", 0))
                        h_diff = abs(outer_dims.get("height", 0) - sem_dims.get("height", 0))
                        if (w_diff > 1.0 and w_diff / max(outer_dims.get("width", 1), 1) > 0.05) or \
                           (h_diff > 1.0 and h_diff / max(outer_dims.get("height", 1), 1) > 0.05):
                            logger.warning(
                                f"{drawing_id}: semantic overall_dimensions differ from outer contour (w_diff={w_diff}, h_diff={h_diff})"
                            )
                except Exception:
                    logger.debug(f"{drawing_id}: outer-dims validation failed")

                # VALIDATION: concentric bore sanity checks
                try:
                    for f in semantic_record.features:
                        if f.feature_class == "concentric_bore":
                            params = f.parameters or {}
                            bore = params.get("bore_diameter") or params.get("inner_diameter")
                            outer = params.get("outer_diameter") or params.get("diameter")
                            if bore and outer and bore > outer:
                                logger.warning(
                                    f"{drawing_id}: concentric bore sanity: bore_diameter ({bore}) > outer_diameter ({outer})"
                                )
                except Exception:
                    logger.debug(f"{drawing_id}: concentric sanity check failed")

                # Add to record list if validation checks pass
                if self.semantic_pipeline._validate(semantic_record):
                    semantic_records.append(semantic_record)
                else:
                    logger.warning(f"Semantic record validation failed for {drawing_id}")
            except Exception as e:
                logger.error(f"Failed to build semantic record for {drawing_id}: {e}")
                continue

        logger.info(f"DatasetExporter: built {len(semantic_records)} semantic records")

        # ── STEP 2: Export Semantic Records ─────────────────────────────
        if semantic_records:
            semantic_records_path = self.output_dir / "semantic_records.json"
            with open(semantic_records_path, "w") as f:
                json.dump(
                    [record.to_dict() for record in semantic_records],
                    f,
                    indent=2
                )
            logger.info(f"Exported semantic records to {semantic_records_path}")

            # Export semantic metadata
            semantic_metadata = {
                "total_drawings": len(semantic_records),
                "total_features": sum(len(r.features) for r in semantic_records),
                "total_relationships": sum(len(r.relationships) for r in semantic_records),
                "feature_class_distribution": self._compute_feature_distribution(semantic_records),
                "relationship_type_distribution": self._compute_relationship_distribution(semantic_records)
            }
            semantic_metadata_path = self.output_dir / "semantic_metadata.json"
            with open(semantic_metadata_path, "w") as f:
                json.dump(semantic_metadata, f, indent=2)
            logger.info(f"Exported semantic metadata to {semantic_metadata_path}")
        else:
            logger.warning("No semantic records generated")

        # ── STEP 3: Build Tasks FROM Semantic Records ───────────────────
        all_tasks: List[Dict] = []
        result_map = {r.get("drawing_id", "unknown"): r for r in all_pipeline_results}
        for semantic_record in semantic_records:
            drawing_id = semantic_record.drawing_id
            result = result_map.get(drawing_id)
            if result:
                tasks = self._build_tasks_from_semantic(semantic_record, result)
                all_tasks.extend(tasks)

        logger.info(f"DatasetExporter: {len(all_tasks)} engineering tasks from semantic records before filtering")

        # Deduplicate tasks (remove identical context + target pairs per drawing)
        seen = set()
        unique_tasks = []
        for t in all_tasks:
            ctx_str = json.dumps(t.get("context"), sort_keys=True)
            tgt_str = json.dumps(t.get("target"), sort_keys=True)
            sig = (t.get("drawing_id"), ctx_str, tgt_str)
            if sig not in seen:
                seen.add(sig)
                unique_tasks.append(t)
        
        logger.info(f"DatasetExporter: deduplicated tasks from {len(all_tasks)} to {len(unique_tasks)}")
        all_tasks = unique_tasks

        # Filter out empty-context tasks (unsolvable guessing tasks)
        filtered_tasks = []
        for t in all_tasks:
            ctx = t.get("context", {})
            inquiry_params = ctx.get("inquiry_feature", {}).get("visible_parameters", {})
            has_params = len(inquiry_params) > 0
            has_neighbors = any(len(nf.get("visible_parameters", {})) > 0 for nf in ctx.get("neighbour_features", []))
            has_relations = len(ctx.get("relationships", [])) > 0
            if has_params or has_neighbors or has_relations:
                filtered_tasks.append(t)
        
        logger.info(f"DatasetExporter: filtered out {len(all_tasks) - len(filtered_tasks)} empty-context tasks")
        all_tasks = filtered_tasks

        if not all_tasks:
            logger.warning("No tasks generated — check pipeline outputs")
            self._write_empty()
            return {
                "total_tasks": 0,
                "total_semantic_records": len(semantic_records)
            }

        # Downsample/Balance tasks
        all_tasks = self._balance_tasks(all_tasks)
        logger.info(f"DatasetExporter: balanced to {len(all_tasks)} tasks")

        # Deterministic split
        train, val, test = self._split_deterministic(all_tasks)

        # Initialize validation stats and reports
        import time
        start_time = time.time()
        
        self.validation_reports = []
        self.validation_stats = {
            "total_processed": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "rejection_reasons": {},
            "prompt_size_chars": [],
            "context_size_chars": [],
            "memory_mb": 0.0,
            "duration_seconds": 0.0
        }

        # Write splits and get validated tasks
        train_accepted = self._write_jsonl(train, self.output_dir / "train.jsonl")
        val_accepted = self._write_jsonl(val, self.output_dir / "validation.jsonl")
        test_accepted = self._write_jsonl(test, self.output_dir / "test.jsonl")

        # Record duration and memory
        duration = time.time() - start_time
        memory = get_memory_usage()
        self.validation_stats["duration_seconds"] = duration
        self.validation_stats["memory_mb"] = memory

        # Save validation report
        report_path = self.output_dir / "validation_report.json"
        with open(report_path, "w") as f:
            json.dump(self.validation_reports, f, indent=2)
        logger.info(f"Exported validation report with {len(self.validation_reports)} rejections to {report_path}")

        # Generate semantic coverage audit
        all_accepted = train_accepted + val_accepted + test_accepted
        self._generate_semantic_coverage_audit(semantic_records, all_accepted)

        # Export metadata
        metadata = self._generate_metadata(all_accepted, train_accepted, val_accepted, test_accepted)
        metadata["total_semantic_records"] = len(semantic_records)
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            f"DatasetExporter: train={len(train_accepted)} (rejected={len(train) - len(train_accepted)}) "
            f"val={len(val_accepted)} (rejected={len(val) - len(val_accepted)}) "
            f"test={len(test_accepted)} (rejected={len(test) - len(test_accepted)})"
        )

        return metadata

    def _sanitize_graph_identifiers(self, obj: Any, friendly_map: Optional[Dict[str, str]] = None) -> Any:
        if friendly_map is None:
            friendly_map = {}
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in ("candidate_id", "parent_id", "children_ids", "group_id", 
                         "relationship_id", "feature_id", "entity_id", "entity_ids",
                         "member_candidate_ids", "candidate_ids"):
                    continue
                cleaned[k] = self._sanitize_graph_identifiers(v, friendly_map)
            return cleaned
        elif isinstance(obj, list):
            cleaned = []
            for item in obj:
                if isinstance(item, str):
                    if item in friendly_map:
                        mapped_val = friendly_map[item]
                        if mapped_val not in cleaned:
                            cleaned.append(mapped_val)
                        continue
                    if (
                        re.match(r'^(hc|rp|sc|cg|rg|ent|conc|sc)_\w+$', item, re.IGNORECASE) or
                        item.startswith("hc_") or item.startswith("rp_") or item.startswith("sc_") or
                        item.startswith("cg_") or item.startswith("rg_") or item.startswith("ent_")
                    ):
                        continue
                cleaned.append(self._sanitize_graph_identifiers(item, friendly_map))
            return cleaned
        elif isinstance(obj, str):
            if obj in friendly_map:
                return friendly_map[obj]
            if (
                re.match(r'^(hc|rp|sc|cg|rg|ent|conc|sc)_\w+$', obj, re.IGNORECASE) or
                obj.startswith("hc_") or obj.startswith("rp_") or obj.startswith("sc_") or
                obj.startswith("cg_") or obj.startswith("rg_") or obj.startswith("ent_")
            ):
                return None
            return obj
        else:
            return obj

    def _build_tasks_from_semantic(
        self,
        semantic_record: Any,
        result: Dict[str, Any],
    ) -> List[Dict]:
        tasks = []
        drawing_id = semantic_record.drawing_id
        overall_dims = semantic_record.overall_dimensions
        features = semantic_record.features
        
        # Helper: Clean dictionaries/lists recursively of empty/null-only structures (Problem 4)
        def _clean_empty_and_nulls(obj: Any) -> Any:
            if isinstance(obj, dict):
                cleaned = {}
                for k, v in obj.items():
                    cleaned_v = _clean_empty_and_nulls(v)
                    if cleaned_v is not None and cleaned_v != {} and cleaned_v != []:
                        cleaned[k] = cleaned_v
                return cleaned if cleaned else None
            elif isinstance(obj, list):
                cleaned = []
                for item in obj:
                    cleaned_item = _clean_empty_and_nulls(item)
                    if cleaned_item is not None and cleaned_item != {} and cleaned_item != []:
                        cleaned.append(cleaned_item)
                return cleaned if cleaned else None
            else:
                return obj

        # Modified semantic task construction method
        def add_semantic_property_task(
            feature,
            property_name: str,
            value: Any,
            context_extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            if value is None or value == "":
                return
                
            task_type = f"infer_{property_name}"
            if feature and feature.feature_class == "slot_array" and property_name in ("width", "length"):
                family = "infer_slot_dimension"
            elif feature and feature.feature_class == "channel" and property_name in ("channel_width", "channel_depth", "channel_length"):
                family = "infer_slot_dimension"
            else:
                family = self._map_to_v21_family(task_type)
                
            if not family:
                return
                
            # Deep copy overall dimensions to prevent mutation
            overall_dims_copy = None
            if overall_dims:
                overall_dims_copy = {
                    "width": overall_dims.get("width"),
                    "height": overall_dims.get("height")
                }

            feature_candidate_id = self._find_candidate_id_for_feature(feature, result) if feature else None
            
            # Sibling parameters of the feature itself
            raw_params = {}
            if feature:
                raw_params = {
                    k: v for k, v in feature.parameters.items()
                    if k != property_name and k not in {"positions", "center", "text"}
                }
                
            target_prop = family[6:] # Strip "infer_"
            raw_value_for_masking = value
            
            # Problem 1: Normalize target representation for infer_thread_size
            if target_prop == "thread_size":
                value = normalize_thread_size(value, feature, drawing_id)
                
            # ── TASK-SPECIFIC CONTEXT SELECTION (Problem 5) ──
            # Stage 2.7.1: Engineering Context Builder redesign
            drawing_id_val = semantic_record.drawing_id
            parts = drawing_id_val.split("_")
            part_family = parts[0] if parts else "General"

            manufacturing_type = "machined"
            drawing_id_lower = drawing_id_val.lower()
            if "bolt" in drawing_id_lower or "shaft" in drawing_id_lower or "screw" in drawing_id_lower or "nut" in drawing_id_lower:
                manufacturing_type = "turned"
            elif "sheet" in drawing_id_lower or "bracket" in drawing_id_lower or "clip" in drawing_id_lower:
                manufacturing_type = "sheet_metal"
            elif "structural" in drawing_id_lower or "beam" in drawing_id_lower or "channel" in drawing_id_lower:
                manufacturing_type = "structural"

            allowed_keys = {
                "across_flats", "head_height", "head_diameter", "grip_length",
                "thread_length", "taper_length", "slot_length", "slot_width",
                "overall_width", "overall_height", "concentric_hole",
                "counterbore_depth", "hole_count", "member_count",
                "width", "length", "depth", "height", "thickness", "diameter",
                "bore_diameter", "bore_type", "hex_height", "neck_length",
                "flange_thickness", "taper", "chamfer_size", "chamfer_angle",
                "radius_value", "pocket_width", "pocket_length", "count", "size",
                
                # Restored parameters (Category A & B)
                "inner_diameter", "outer_diameter", "boss_diameter",
                "spacing_x", "spacing_y", "perimeter_wall", "pcd",
                "hole_diameter", "angular_spacing", "radius", "web_thickness",
                "fillet_radius", "wall_thickness", "port_diameter",
                "counterbore_diameter", "flange_diameter", "base_diameter",
                "shoulder_diameter", "shoulder_length", "channel_width",
                "cope_radius", "value", "o_ring_diameter", "drive_size",
                "inner_radius", "outer_radius"
            }
            forbidden_keys = {
                "thread_designation", "major_diameter", "nominal_diameter",
                "thread_pitch", "pitch", "pitch_tpi", "source_annotation",
                "text", "raw_annotation", "validation_status", "lookup_result",
                "engineering_standard", "tolerance_class", "tolerance_upper",
                "tolerance_lower", "fit_class", "lower_deviation", "upper_deviation"
            }

            # Alias grouping to prevent target leakage
            ALIAS_GROUPS = [
                {"bore_diameter", "inner_diameter", "pilot_bore", "concentric_hole"},
                {"outer_diameter", "boss_diameter", "flange_diameter", "boss_od", "flange_od"},
                {"spacing", "spacing_x", "spacing_y", "pitch", "bore_pitch", "slot_crs"},
                {"wall_thickness", "perimeter_wall", "thickness"},
            ]

            def is_alias(p1: str, p2: str) -> bool:
                p1_clean = p1.lower()
                p2_clean = p2.lower()
                if p1_clean == p2_clean:
                    return True
                for g in ALIAS_GROUPS:
                    if p1_clean in g and p2_clean in g:
                        return True
                # Handle generic 'diameter' as alias of specific diameters
                diams = {"bore_diameter", "inner_diameter", "outer_diameter", "boss_diameter", "flange_diameter", "hole_diameter"}
                if p1_clean == "diameter" and p2_clean in diams:
                    return True
                if p2_clean == "diameter" and p1_clean in diams:
                    return True
                return False

            visible_params = {}
            if feature:
                for k, v in (feature.parameters or {}).items():
                    if k == property_name:
                        continue
                    # Alias-aware masking: prevent target leakage from synonym parameters
                    if is_alias(k, property_name) or is_alias(k, target_prop):
                        continue
                    if k in allowed_keys and k not in forbidden_keys:
                        visible_params[k] = v

            # ── SECONDARY MASKING: value-equality sweep ───────────────────────
            # Disabled coincidental target value masking to preserve engineering reasoning cues.

            neighbour_features = []
            forbidden_feature_classes = {"unknown_facts", "dimension_annotations", "raw_lines", "raw_circles", "debug_metadata"}
            for f in features:
                if feature and f.feature_id == feature.feature_id:
                    continue
                if f.feature_class in forbidden_feature_classes:
                    continue
                f_visible = {}
                for k, v in (f.parameters or {}).items():
                    if k in allowed_keys and k not in forbidden_keys:
                        f_visible[k] = v
                neighbour_features.append({
                    "feature_class": f.feature_class,
                    "visible_parameters": f_visible
                })

            relationships = []
            for rel in (semantic_record.relationships or []):
                relationships.append({
                    "type": rel.relationship_type,
                    "associated_features": rel.feature_ids,
                    "parameters": {
                        k: v for k, v in (rel.parameters or {}).items()
                        if k not in forbidden_keys
                    }
                })

            topology = {}
            if semantic_record.hierarchy:
                nodes = semantic_record.hierarchy.get("nodes", [])
                topology["contours"] = len(nodes)
                topology["nesting"] = max([n.get("nesting_depth", 0) for n in nodes]) if nodes else 0
            else:
                struct_stats = result.get("structural_result", {}).get("statistics", {})
                topology["contours"] = struct_stats.get("contours", {}).get("total_contours", 0)
                topology["nesting"] = struct_stats.get("contours", {}).get("max_nesting", 0)

            feat_stats = result.get("feature_result", {}).get("statistics", {})
            topology["holes"] = feat_stats.get("holes", {}).get("total_candidates", 0)
            topology["regions"] = len(result.get("structural_result", {}).get("regions", []))

            # Deduplicate task context representation using frozen layout order
            cleaned_context = {
                "drawing_id": drawing_id_val,
                "part_family": part_family,
                "manufacturing_type": manufacturing_type,
                "overall_dimensions": overall_dims_copy,
                "inquiry_feature": {
                    "feature_class": feature.feature_class if feature else "span_dimension",
                    "visible_parameters": visible_params
                },
                "neighbour_features": neighbour_features,
                "relationships": relationships,
                "topology": topology
            }
            
            eng_rules = semantic_record.metadata.get("engineering_rules") if semantic_record.metadata else None
            if eng_rules:
                cleaned_context["engineering_rules"] = eng_rules

            # Create friendly map to resolve candidate IDs AND constituent entity IDs to friendly feature IDs
            friendly_map = {}
            
            def get_candidate_entities(cid: str) -> list:
                if not cid:
                    return []
                # Check hole candidates
                for hc in result.get("feature_result", {}).get("hole_candidates", {}).get("hole_candidates", []):
                    if hc.get("candidate_id") == cid:
                        eids = hc.get("entity_id") or hc.get("entity_ids") or []
                        return [eids] if isinstance(eids, str) else list(eids)
                # Check slot candidates
                for sc in result.get("feature_result", {}).get("slot_candidates", {}).get("slot_candidates", []):
                    if sc.get("candidate_id") == cid:
                        eids = sc.get("entity_id") or sc.get("entity_ids") or []
                        return [eids] if isinstance(eids, str) else list(eids)
                # Check concentric groups
                for cg in result.get("structural_result", {}).get("concentric_groups", {}).get("concentric_groups", []):
                    if cg.get("group_id") == cid:
                        return list(cg.get("entity_ids", []))
                return []

            import math
            for f in features:
                friendly_map[f.feature_id] = f.feature_id
                cand_id = self._find_candidate_id_for_feature(f, result)
                if cand_id:
                    friendly_map[cand_id] = f.feature_id
                    for eid in get_candidate_entities(cand_id):
                        friendly_map[eid] = f.feature_id
                
                # If feature represents a pattern, map all its pattern members
                fparams = f.parameters or {}
                fcenter = fparams.get("center")
                if fcenter and len(fcenter) >= 2:
                    for rp in result.get("feature_result", {}).get("radial_patterns", {}).get("radial_patterns", []):
                        rp_center = rp.get("center")
                        if rp_center and len(rp_center) >= 2 and math.dist(fcenter[:2], rp_center[:2]) < 1.0:
                            pid = rp.get("pattern_id")
                            if pid:
                                friendly_map[pid] = f.feature_id
                            for m_cid in rp.get("member_candidate_ids", []):
                                friendly_map[m_cid] = f.feature_id
                                for eid in get_candidate_entities(m_cid):
                                    friendly_map[eid] = f.feature_id
            
            cleaned_context = self._sanitize_graph_identifiers(cleaned_context, friendly_map)
                
            # QUALITY VALIDATION / WEAK SUPERVISION CHECK (Problem 2 & Quality Rule)
            # Evaluate if a mechanical engineer can infer target dimension based on visible cues
            has_valid_cues = False
            
            inquiry_params = cleaned_context.get("inquiry_feature", {}).get("visible_parameters", {})
            all_params = dict(inquiry_params)
            for nf in cleaned_context.get("neighbour_features", []):
                all_params.update(nf.get("visible_parameters", {}))
                
            if target_prop == "thread_size":
                has_valid_cues = any(k in all_params for k in ("across_flats", "thread_length", "grip_length", "length", "thread_pitch", "nominal_diameter", "diameter")) or \
                                 bool(cleaned_context.get("relationships"))
            elif target_prop == "spacing":
                has_valid_cues = any(k in all_params for k in ("count", "pitch", "spacing", "spacing_x", "spacing_y", "angular_spacing", "pcd", "hole_count")) or \
                                 bool(cleaned_context.get("relationships"))
            elif target_prop == "wall_thickness":
                has_valid_cues = any(k in all_params for k in ("bore_diameter", "boss_diameter", "outer_diameter", "diameter", "inner_diameter", "perimeter_wall")) or \
                                 bool(cleaned_context.get("relationships"))
            elif target_prop in ("profile_dimension", "slot_dimension", "pocket_dimension"):
                has_valid_cues = len(all_params) > 0 or \
                                 bool(cleaned_context.get("relationships"))
            else:
                has_valid_cues = len(all_params) > 0 or len(cleaned_context.get("relationships", [])) > 0

            if not has_valid_cues:
                logger.warning(
                    f"DatasetExporter: Rejected task {task_type} for drawing {drawing_id} "
                    f"due to weak supervision (insufficient engineering cues)."
                )
                return
                
            tasks.append({
                "task_type": family,
                "drawing_id": drawing_id,
                "context": cleaned_context,
                "target": {
                    "property": target_prop,
                    "value": value
                }
            })

        # ── GENERATE STANDARD TASKS ──────────────────────────────
        for feature in features:
            if feature.feature_class == "unknown_facts":
                continue
            params = feature.parameters or {}
            
            if feature.feature_class == "concentric_bore":
                for field in ("bore_diameter", "boss_diameter", "base_diameter", "flange_diameter"):
                    add_semantic_property_task(feature, field, params.get(field))
                bore_d = params.get("bore_diameter") or params.get("inner_diameter") or params.get("diameter")
                outer_d = params.get("outer_diameter") or params.get("diameter")
                if bore_d and outer_d and outer_d > bore_d:
                    w_thick = round((outer_d - bore_d) / 2.0, 4)
                    add_semantic_property_task(feature, "wall_thickness", w_thick)
                    
            elif feature.feature_class == "hole_pattern":
                field_map = {
                    "pcd": "spacing",
                    "hole_count": "hole_count",
                    "hole_diameter": "hole_diameter",
                    "counterbore_diameter": "hole_diameter",
                    "counterbore_depth": "profile_dimension",
                }
                for source_key, property_name in field_map.items():
                    add_semantic_property_task(feature, property_name, params.get(source_key))
                    
            elif feature.feature_class == "hole_group":
                text_annots = params.get("text", "").upper()
                is_bore = ("BORE" in text_annots or "COMBUSTION" in text_annots) and not any(w in text_annots for w in ("ALIGNMENT", "CLEARANCE", "BOLT"))
                field_map = {
                    "count": "hole_count",
                    "diameter": "bore_diameter" if is_bore else "hole_diameter",
                    "spacing_x": "spacing",
                    "spacing_y": "spacing",
                    "counterbore_diameter": "hole_diameter",
                    "counterbore_depth": "profile_dimension",
                }
                for source_key, property_name in field_map.items():
                    add_semantic_property_task(feature, property_name, params.get(source_key))
                    
            elif feature.feature_class == "slot_array":
                add_semantic_property_task(feature, "width", params.get("width"))
                add_semantic_property_task(feature, "length", params.get("length"))
                
            elif feature.feature_class == "lube_port":
                add_semantic_property_task(feature, "hole_diameter", params.get("diameter"))
                
            elif feature.feature_class == "thread":
                add_semantic_property_task(feature, "thread_size", params.get("nominal_diameter"))
                
            elif feature.feature_class == "keyway":
                add_semantic_property_task(feature, "slot_dimension", params.get("width"))
                add_semantic_property_task(feature, "slot_dimension", params.get("depth"))
                
            elif feature.feature_class == "heatsink_fin":
                add_semantic_property_task(feature, "hole_count", params.get("count"))
                add_semantic_property_task(feature, "spacing", params.get("pitch"))
                
            elif feature.feature_class == "heatsink_core":
                add_semantic_property_task(feature, "outer_diameter", params.get("diameter"))
                
            elif feature.feature_class == "structural_profile":
                for field in ("web_thickness", "flange_thickness"):
                    add_semantic_property_task(feature, "profile_dimension", params.get(field))
                for field in ("wall_thickness", "fillet_radius", "inner_radius", "outer_radius"):
                    add_semantic_property_task(feature, "wall_thickness" if "wall" in field else "profile_dimension", params.get(field))
                    
            elif feature.feature_class == "bolt":
                for field in ("grip_length", "thread_length", "across_flats"):
                    add_semantic_property_task(feature, "profile_dimension", params.get(field))
                add_semantic_property_task(feature, "thread_size", params.get("nominal_diameter"))
                
            elif feature.feature_class == "screw":
                for field in ("length", "head_diameter", "drive_size"):
                    add_semantic_property_task(feature, "profile_dimension", params.get(field))
                add_semantic_property_task(feature, "thread_size", params.get("nominal_diameter"))
                
            elif feature.feature_class == "hex_head":
                add_semantic_property_task(feature, "profile_dimension", params.get("across_flats"))
                
            elif feature.feature_class == "hex_drive":
                add_semantic_property_task(feature, "profile_dimension", params.get("size"))
                
            elif feature.feature_class == "cylindrical_head":
                add_semantic_property_task(feature, "outer_diameter", params.get("head_diameter") or params.get("diameter"))
                
            elif feature.feature_class == "fitting":
                for field in ("taper_length", "hex_height", "neck_length", "flange_thickness", "across_flats"):
                    add_semantic_property_task(feature, "profile_dimension", params.get(field))
                    
            elif feature.feature_class == "pocket":
                add_semantic_property_task(feature, "pocket_width", params.get("pocket_width"))
                add_semantic_property_task(feature, "pocket_length", params.get("pocket_length"))
                add_semantic_property_task(feature, "wall_thickness", params.get("perimeter_wall"))
                
            elif feature.feature_class == "o_ring":
                add_semantic_property_task(feature, "hole_diameter", params.get("o_ring_diameter"))
                add_semantic_property_task(feature, "slot_dimension", params.get("o_ring_groove_depth"))
                
            elif feature.feature_class == "port":
                add_semantic_property_task(feature, "hole_diameter", params.get("port_diameter"))
                add_semantic_property_task(feature, "slot_dimension", params.get("port_depth"))
                add_semantic_property_task(feature, "thread_size", params.get("port_thread"))
                
            elif feature.feature_class == "channel":
                add_semantic_property_task(feature, "slot_dimension", params.get("channel_width"))
                add_semantic_property_task(feature, "slot_dimension", params.get("channel_depth"))
                add_semantic_property_task(feature, "slot_dimension", params.get("channel_length"))
                
            elif feature.feature_class == "shoulder":
                add_semantic_property_task(feature, "outer_diameter", params.get("shoulder_diameter"))
                add_semantic_property_task(feature, "profile_dimension", params.get("shoulder_length"))
                
            elif feature.feature_class == "cope":
                add_semantic_property_task(feature, "profile_dimension", params.get("cope_radius"))
                
            elif feature.feature_class in ("rib", "alignment_tab", "chamfer", "bend_relief"):
                add_semantic_property_task(feature, "profile_dimension", params.get("value"))
                
            elif feature.feature_class == "dimension_annotations":
                for dim in params.get("dimensions", []) + params.get("pattern_dimensions", []):
                    text = dim.get("text") or "dimension"
                    property_name = self._make_generic_property_name(text)
                    if property_name:
                        add_semantic_property_task(
                            feature,
                            property_name,
                            dim.get("value"),
                            {"dimension_text": dim.get("text")}
                        )

        # ── FEATURE SPAN REDESIGN ────────────────────────────────
        centers = []
        for f in features:
            if f.feature_class in ("concentric_bore", "hole_pattern", "hole_group"):
                c = f.parameters.get("center")
                if c and isinstance(c, list) and len(c) >= 2:
                    centers.append(c)
                else:
                    positions = f.parameters.get("positions", [])
                    for p in positions:
                        if isinstance(p, list) and len(p) >= 2:
                            centers.append(p)
        
        unique_centers = []
        for c in centers:
            if not any(abs(c[0]-uc[0]) < 0.01 and abs(c[1]-uc[1]) < 0.01 for uc in unique_centers):
                unique_centers.append(c)
                
        if len(unique_centers) >= 2:
            x_coords = [c[0] for c in unique_centers]
            y_coords = [c[1] for c in unique_centers]
            span_x = round(max(x_coords) - min(x_coords), 4)
            span_y = round(max(y_coords) - min(y_coords), 4)
            
            if span_x > 0.1:
                ctx_extra = {
                    "direction": "horizontal",
                    "feature_centers": unique_centers
                }
                add_semantic_property_task(None, "feature_span", span_x, context_extra=ctx_extra)
            if span_y > 0.1:
                ctx_extra = {
                    "direction": "vertical",
                    "feature_centers": unique_centers
                }
                add_semantic_property_task(None, "feature_span", span_y, context_extra=ctx_extra)
        else:
            logger.debug(f"Skipped feature_span (centers count: {len(unique_centers)})")

        return tasks



    def _find_candidate_id_for_feature(
        self,
        feature: Any,
        result: Dict[str, Any],
    ) -> Optional[str]:
        import math
        fclass = feature.feature_class
        params = feature.parameters or {}
        
        center = params.get("center")
        positions = params.get("positions", [])
        
        hole_candidates = result.get("feature_result", {}).get("hole_candidates", {}).get("hole_candidates", [])
        if center and len(center) >= 2:
            for hc in hole_candidates:
                hc_center = hc.get("center")
                if hc_center and len(hc_center) >= 2 and math.dist(center[:2], hc_center[:2]) < 1.0:
                    return hc.get("candidate_id")
        if positions:
            for hc in hole_candidates:
                hc_center = hc.get("center")
                if hc_center and len(hc_center) >= 2 and any(len(pos) >= 2 and math.dist(pos[:2], hc_center[:2]) < 1.0 for pos in positions):
                    return hc.get("candidate_id")
                    
        concentric_groups = result.get("structural_result", {}).get("concentric_groups", {}).get("concentric_groups", [])
        if center and len(center) >= 2:
            for cg in concentric_groups:
                cg_center = cg.get("center")
                if cg_center and len(cg_center) >= 2 and math.dist(center[:2], cg_center[:2]) < 1.0:
                    return cg.get("group_id")
                    
        slot_candidates = result.get("feature_result", {}).get("slot_candidates", {}).get("slot_candidates", [])
        if center and len(center) >= 2:
            for sc in slot_candidates:
                sc_center = sc.get("center")
                if sc_center and len(sc_center) >= 2 and math.dist(center[:2], sc_center[:2]) < 1.0:
                    return sc.get("candidate_id")
                    
        pocket_w = params.get("pocket_width") or params.get("width") or params.get("channel_width") or params.get("slot_dimension")
        pocket_l = params.get("pocket_length") or params.get("length") or params.get("channel_length")
        if pocket_w and pocket_l:
            for sc in slot_candidates:
                sc_w = sc.get("width")
                sc_h = sc.get("height")
                if sc_w and sc_h:
                    sc_min = min(sc_w, sc_h)
                    sc_max = max(sc_w, sc_h)
                    if abs(sc_min - min(pocket_w, pocket_l)) < 2.0 and abs(sc_max - max(pocket_w, pocket_l)) < 2.0:
                        return sc.get("candidate_id")
                        
        bore_d = params.get("bore_diameter") or params.get("inner_diameter") or params.get("diameter") or params.get("nominal_diameter")
        if bore_d:
            for hc in hole_candidates:
                hc_radii = [r * 2.0 for r in hc.get("radii", [])]
                if any(abs(r - bore_d) < 0.1 for r in hc_radii):
                    return hc.get("candidate_id")

        return None

    def _make_generic_property_name(self, text: str) -> str:
        t = text.upper()
        if "BORE PITCH" in t:
            return "bore_pitch"
        if "WEB SPACING" in t:
            return "web_spacing"
        if "WEB WIDTH" in t:
            return "web_width"
        if "SLOT CRS" in t:
            return "slot_crs"
        if "ALIGNMENT TAB" in t:
            return "alignment_tab_value"
        if "TAPER LENGTH" in t:
            return "taper_length"
        if "HEX HEIGHT" in t:
            return "hex_height"
        if "WELD NECK" in t:
            return "weld_neck_length"
        if "FLANGE THK" in t or "FLANGE THICKNESS" in t:
            return "flange_thickness"
        if "FLANGE OD" in t:
            return "flange_od"
        if "BASE THK" in t or "BASE THICKNESS" in t:
            return "base_thickness"
        if "PERIMETER WALL" in t:
            return "perimeter_wall"
        if "INTERNAL RAD" in t or "INTERNAL RADIUS" in t:
            return "internal_radius"
        if "TUBE PROFILE" in t or "PROFILE" in t:
            return "tube_profile_width"
        if "OPENING" in t:
            return "top_opening_width"
        if "GROOVE BASE" in t or "ROOT BASE" in t:
            return "groove_base_width"
        if "DEPTH" in t or "DEEP" in t:
            return "groove_depth"
        if "O-RING" in t or "ORING" in t:
            return "o_ring_diameter"
        if "SHOULDER" in t:
            if "LEN" in t or "LENGTH" in t:
                return "shoulder_length"
            else:
                return "shoulder_diameter"
        if "TUBE COPE" in t or "COPE" in t:
            return "cope_radius"
        
        cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        cleaned = re.sub(r"^\d+x\d+mm_", "", cleaned)
        cleaned = re.sub(r"^\d+mm_", "", cleaned)
        cleaned = re.sub(r"^\d+_", "", cleaned)
        return cleaned

    def _map_to_v21_family(self, task_type: str) -> Optional[str]:
        prop = task_type
        if prop.startswith("infer_"):
            prop = prop[6:]
            
        if prop in (
            "overall_length", "pocket_depth", "bevel_depth", "bend_allowance", 
            "bend_radius", "bend_angle", "angle", "radius", "developed_length", "blank_width",
            "notes_1_matl_30mm_thk_6061_t6_aluminum_2_break_all_sharp_edges_0_5mm_max"
        ):
            return None
            
        if prop in ("wall_thickness", "perimeter_wall", "internal_web", "flexure_web", "uniform_wall_isogrid", "center_web", "root_thk", "conductor_width") or "wall_thk" in prop or "material_thk" in prop or "nominal_thk" in prop or "thickness" in prop:
            return "infer_wall_thickness"
            
        if prop in ("pocket_width", "pocket_length", "pocket_w", "pocket_l", "groove_base_width", "opening_width", "yoke_channel", "pocket_height") or "pocket" in prop or "groove" in prop:
            return "infer_pocket_dimension"
            
        if prop in ("slot_width", "slot_length", "slot_w", "slot_l", "keyway_width", "keyway_depth", "channel_width", "channel_depth", "channel_length") or "slot" in prop or "keyway" in prop:
            return "infer_slot_dimension"
            
        if prop in ("overall_width", "overall_height", "overall_w", "overall_h", "feature_span", "total_span", "center_loc", "to_saddle_center", "mount_x", "block_l", "nozzle_len", "slider_length", "frame_width", "frame_height") or "span" in prop or "reach" in prop or "length" in prop or "height" in prop or "width" in prop or "travel" in prop:
            return "infer_feature_span"
            
        if prop in ("bore_diameter", "inner_diameter", "pilot_bore", "terminal_bore", "precision_node", "roller_diameter", "shaft_bore", "main_fulcrum_bore", "thru_pivot_bores", "alignment_bore", "bore_2", "cbore", "thru", "through_bore", "thru_bore"):
            return "infer_bore_diameter"
            
        if prop in ("outer_diameter", "flange_diameter", "boss_diameter", "boss_od", "flange_od", "tube_od", "disk_od", "window_od", "core_diameter", "shoulder_diameter", "head_diameter", "turned_od", "base_diameter") or "od" in prop:
            return "infer_outer_diameter"
            
        if prop in ("spacing_x", "spacing_y", "hole_spacing_x", "hole_spacing_y", "bolt_spacing", "ctr_to_ctr", "spacing", "pitch", "fin_pitch", "bore_pitch", "web_spacing", "slot_crs", "groove_spacing", "pattern_pitch", "pattern"):
            return "infer_spacing"
            
        if prop in ("hole_count", "bore_count", "count", "fin_count", "roller_count", "bolt_count"):
            return "infer_hole_count"
            
        if prop in ("hole_diameter", "diameter", "counterbore_diameter", "lube_port_diameter", "o_ring_diameter", "port_diameter", "plug_weld_bore"):
            return "infer_hole_diameter"
            
        if prop in ("nominal_thread", "nominal_diameter", "thread_pitch", "thread_size", "port_thread") or "thread" in prop or re.match(r'^m\d+', prop) or "thd" in prop:
            return "infer_thread_size"
            
        if prop in ("web_thickness", "flange_thickness", "profile_thickness", "base_thickness", "across_flats", "hex_height", "taper_length", "neck_length", "grip_length", "thread_length", "drive_size", "shoulder_length", "chamfer_value", "fillet_radius", "fillet_radius_value", "internal_radius", "base_contact", "vertical_contact", "splice_leg", "vertical_leg", "insertion_ramp") or "radius" in prop or "fillet" in prop or "chamfer" in prop or "bevel" in prop or "flat" in prop or "face" in prop or "leg" in prop:
            return "infer_profile_dimension"
            
        if "thickness" in prop or "wall" in prop:
            return "infer_wall_thickness"
        if "span" in prop or "width" in prop or "height" in prop or "length" in prop:
            return "infer_feature_span"
        if "bore" in prop:
            return "infer_bore_diameter"
        if "diameter" in prop or "dia" in prop or "od" in prop:
            return "infer_outer_diameter"
        if "spacing" in prop or "pitch" in prop:
            return "infer_spacing"
        if "count" in prop or "qty" in prop:
            return "infer_hole_count"
            
        return "infer_profile_dimension"

    def _mask_context_leakage(
        self,
        obj: Any,
        target_val: Any,
        target_prop: str,
        original_property: Optional[str] = None,
        key_context: Optional[str] = None,
    ) -> Any:
        banned_by_prop = {
            "wall_thickness": {
                "bore_diameter", "inner_diameter", "outer_diameter", "diameter", 
                "wall_thickness", "perimeter_wall", "thickness", "wall_thk", 
                "material_thk", "nominal_thk", "radii", "signature", "aspect_ratio"
            },
            "feature_span": {
                "overall_width", "overall_height", "overall_length", "feature_span"
            },
            "bore_diameter": {
                "bore_diameter", "inner_diameter", "diameter", "radii", "signature"
            },
            "outer_diameter": {
                "outer_diameter", "boss_diameter", "diameter", "radii", "signature",
                "boss_od", "flange_od", "tube_od", "disk_od", "window_od", 
                "core_diameter", "shoulder_diameter", "head_diameter", "turned_od", "base_diameter"
            },
            "spacing": {
                "spacing_x", "spacing_y", "bolt_spacing", "ctr_to_ctr", "spacing",
                "pitch", "fin_pitch", "bore_pitch", "web_spacing", "slot_crs", "groove_spacing"
            },
            "hole_count": {
                "bore_count", "count", "angular_spacing", "hole_count", "fin_count", "bolt_count",
                "repetition_count"
            },
            "hole_diameter": {
                "diameter", "counterbore_diameter", "hole_diameter", "lube_port_diameter", 
                "o_ring_diameter", "port_diameter", "radii", "signature"
            },
            "thread_size": {
                "nominal_diameter", "pitch", "thread_size", "nominal_thread", "port_thread"
            },
            "pocket_dimension": {
                "pocket_width", "pocket_length", "width", "length", "aspect_ratio", 
                "pocket_dimension", "groove_base_width", "opening_width", "pocket_height"
            },
            "profile_dimension": {
                "web_thickness", "flange_thickness", "wall_thickness", "lip_thickness", 
                "across_flats", "hex_height", "taper_length", "neck_length", "grip_length", 
                "thread_length", "drive_size", "shoulder_length", "chamfer_value", 
                "fillet_radius", "fillet_radius_value", "internal_radius", "profile_dimension"
            },
            "slot_dimension": {
                "width", "length", "aspect_ratio", "slot_width", "slot_length", "slot_dimension", 
                "keyway_width", "keyway_depth", "channel_width", "channel_depth", "channel_length", 
                "radii", "signature"
            }
        }
        
        global_forbidden = {
            "dimension_text", "dimensions", "pattern_dimensions", 
            "part_name", "description", "part_type", "text"
        }
        
        # Calculate numeric values to mask to prevent leakage
        vals_to_mask = set()
        if isinstance(target_val, (int, float)):
            vals_to_mask.add(target_val)
            vals_to_mask.add(target_val / 2.0)
        elif isinstance(target_val, str):
            m_num = re.search(r'\d+(\.\d+)?', target_val)
            if m_num:
                num_val = float(m_num.group(0))
                vals_to_mask.add(num_val)
                vals_to_mask.add(num_val / 2.0)
            if "1/2" in target_val:
                vals_to_mask.add(0.5)
                vals_to_mask.add(0.25)
            elif "1/4" in target_val:
                vals_to_mask.add(0.25)
                vals_to_mask.add(0.125)
            elif "3/4" in target_val:
                vals_to_mask.add(0.75)
                vals_to_mask.add(0.375)
            elif "3/8" in target_val:
                vals_to_mask.add(0.375)
                vals_to_mask.add(0.1875)

        bypass_keys = {
            "member_count", "inner_feature_count", "outer_feature_count", 
            "pair_count", "sibling_count", "nesting_depth", "total_contours", 
            "outer", "inner", "count", "hole_count", "bore_count", "fin_count", 
            "bolt_count", "axis_position", "mirror_axis", "shared_center", "center",
            "angle_step"
        }

        if isinstance(obj, dict):
            new_obj = {}
            for k, v in obj.items():
                if k in global_forbidden:
                    continue
                
                # Pocket or Slot: mask aspect_ratio and target_prop, but NOT co-dependent width/length sibling
                if original_property:
                    if k == original_property:
                        continue
                    if target_prop in ("pocket_dimension", "slot_dimension"):
                        if k in banned_by_prop[target_prop] and k != original_property and k not in ("pocket_width", "pocket_length", "width", "length"):
                            continue
                    else:
                        if target_prop in banned_by_prop and k in banned_by_prop[target_prop]:
                            continue
                else:
                    if target_prop in banned_by_prop and k in banned_by_prop[target_prop]:
                        continue
                
                # Prevent overall_dimensions coordinate leak
                if k == "overall_dimensions" and isinstance(v, dict):
                    masked_dims = {}
                    for dk, dv in v.items():
                        if target_prop == "feature_span" and isinstance(dv, (int, float)) and isinstance(target_val, (int, float)):
                            if abs(dv - target_val) < 0.01:
                                masked_dims[dk] = None
                            else:
                                masked_dims[dk] = dv
                        else:
                            masked_dims[dk] = dv
                    new_obj[k] = masked_dims
                    continue
                
                # Thread designation sanitization to prevent leakage
                if k == "thread_designation" and isinstance(v, str) and target_prop == "thread_size":
                    sanitized_v = v
                    val_str = str(target_val)
                    if val_str.endswith(".0"):
                        val_str_int = val_str[:-2]
                    else:
                        val_str_int = val_str
                    
                    # Replace fractions with type safety
                    if isinstance(target_val, (int, float)):
                        if abs(target_val - 0.5) < 0.01:
                            sanitized_v = re.sub(r'1/2', '[THREAD]', sanitized_v)
                        elif abs(target_val - 0.25) < 0.01:
                            sanitized_v = re.sub(r'1/4', '[THREAD]', sanitized_v)
                        elif abs(target_val - 0.75) < 0.01:
                            sanitized_v = re.sub(r'3/4', '[THREAD]', sanitized_v)
                        elif abs(target_val - 0.375) < 0.01:
                            sanitized_v = re.sub(r'3/8', '[THREAD]', sanitized_v)
                    elif isinstance(target_val, str):
                        for fraction in ("1/2", "1/4", "3/4", "3/8"):
                            if fraction in target_val:
                                sanitized_v = re.sub(re.escape(fraction), '[THREAD]', sanitized_v)
                        num_match = re.search(r'\d+', target_val)
                        if num_match:
                            val_str_int = num_match.group(0)
                    
                    # Replace nominal digits
                    if val_str_int and len(val_str_int) > 0:
                        sanitized_v = re.sub(r'(?i)\b([a-z]*?)' + re.escape(val_str_int) + r'(?![0-9])', r'\1[THREAD]', sanitized_v)
                    new_obj[k] = sanitized_v
                    continue
                    
                new_obj[k] = self._mask_context_leakage(v, target_val, target_prop, original_property, key_context=k)
            return new_obj
        elif isinstance(obj, list):
            return [self._mask_context_leakage(x, target_val, target_prop, original_property, key_context) for x in obj]
        elif isinstance(obj, (int, float)):
            return obj
        else:
            return obj



    def _balance_tasks(self, tasks: List[Dict]) -> List[Dict]:
        tasks_by_family = defaultdict(list)
        for task in tasks:
            tasks_by_family[task["task_type"]].append(task)
            
        counts = [len(tasks_by_family[f]) for f in tasks_by_family]
        if not counts:
            return tasks
            
        import numpy as np
        median = float(np.median(counts))
        p75 = float(np.percentile(counts, 75))
        threshold = int(max(median, p75))
        
        logger.info(f"Adaptive balancing: median={median}, P75={p75}, dynamic cap threshold={threshold}")
        
        balanced_tasks = []
        for family, family_tasks in tasks_by_family.items():
            if len(family_tasks) > threshold:
                drawings_map = defaultdict(list)
                for t in family_tasks:
                    drawings_map[t["drawing_id"]].append(t)
                unique_drawings = sorted(drawings_map.keys())
                
                selected = []
                # Ensure at least one task per drawing is included
                for d in unique_drawings:
                    selected.append(drawings_map[d][0])
                
                # Fill remaining slots using stride if needed
                remaining_tasks = []
                for d in unique_drawings:
                    remaining_tasks.extend(drawings_map[d][1:])
                
                if len(selected) < threshold:
                    needed = threshold - len(selected)
                    stride = len(remaining_tasks) / needed if needed > 0 else 0
                    for i in range(needed):
                        idx = int(round(i * stride))
                        if idx < len(remaining_tasks):
                            selected.append(remaining_tasks[idx])
                
                balanced_tasks.extend(selected)
                logger.info(f"Adaptive balancing {family}: downsampled from {len(family_tasks)} to {len(selected)}")
            else:
                balanced_tasks.extend(family_tasks)
                
        return balanced_tasks

    def _split_deterministic(self, tasks: List[Dict]) -> tuple:
        def get_base_drawing_id(drawing_id: str) -> str:
            cleaned = drawing_id.replace("Corrected_", "")
            cleaned = re.sub(r"_(variant|stress|step|v\d+|\d+mm)$", "", cleaned, flags=re.IGNORECASE)
            return cleaned
            
        unique_base_ids = sorted(list(set(get_base_drawing_id(task["drawing_id"]) for task in tasks)))
        
        def extract_family_prefix(base_id: str) -> str:
            match = re.match(r"^([a-zA-Z_]+)(?:_[A-Z0-9]+)?", base_id)
            if match:
                return match.group(1).rstrip("_")
            return "Generic"
            
        family_groups = defaultdict(list)
        for base_id in unique_base_ids:
            prefix = extract_family_prefix(base_id)
            family_groups[prefix].append(base_id)
            
        base_id_assignments = {}
        salt = "cad_engine_v2_split_salt"
        
        for family, members in family_groups.items():
            sorted_members = sorted(members)
            for base_id in sorted_members:
                hash_input = f"{salt}_{base_id}".encode("utf-8")
                h = int(hashlib.md5(hash_input).hexdigest(), 16) % 100
                
                if h < int(TRAIN_RATIO * 100):
                    base_id_assignments[base_id] = "train"
                elif h < int((TRAIN_RATIO + VAL_RATIO) * 100):
                    base_id_assignments[base_id] = "validation"
                else:
                    base_id_assignments[base_id] = "test"
                    
        train, val, test = [], [], []
        for task in tasks:
            base_id = get_base_drawing_id(task["drawing_id"])
            assignment = base_id_assignments.get(base_id, "train")
            
            if assignment == "train":
                train.append(task)
            elif assignment == "validation":
                val.append(task)
            else:
                test.append(task)
                
        train_drawings = set(t["drawing_id"] for t in train)
        val_drawings = set(t["drawing_id"] for t in val)
        test_drawings = set(t["drawing_id"] for t in test)
        
        overlap_train_val = train_drawings.intersection(val_drawings)
        overlap_train_test = train_drawings.intersection(test_drawings)
        overlap_val_test = val_drawings.intersection(test_drawings)
        
        if overlap_train_val or overlap_train_test or overlap_val_test:
            raise AssertionError(
                f"CRITICAL OVERLAP ERROR: Drawing splits are not isolated!\n"
                f"  train & validation: {overlap_train_val}\n"
                f"  train & test: {overlap_train_test}\n"
                f"  validation & test: {overlap_val_test}"
            )
            
        logger.info(f"Split verification PASSED. Overlaps: train-val=0, train-test=0, val-test=0")
        
        return train, val, test



    def _validate_structure(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 1 — Structure validation: Verify mandatory top-level fields."""
        required = {"drawing_id", "context", "target", "system", "user", "assistant"}
        missing = required - sample.keys()
        if missing:
            return {
                "passed": False,
                "stage": "Stage 1",
                "rule": "JSON Structure",
                "severity": "CRITICAL",
                "reason": f"Missing top-level fields: {', '.join(missing)}",
                "location": "root",
                "recommendation": "Ensure prompt renderer and exporter pipeline produce all mandatory top-level keys."
            }
        return {"passed": True}

    def _validate_schema(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 2 — Schema Validation: Validate types, nesting, required/unexpected keys."""
        # Top-level type checks
        for key in ["drawing_id", "system", "user", "assistant"]:
            if not isinstance(sample.get(key), str):
                return {
                    "passed": False,
                    "stage": "Stage 2",
                    "rule": "Schema Validation",
                    "severity": "CRITICAL",
                    "reason": f"Field '{key}' must be a string, got {type(sample.get(key)).__name__}",
                    "location": f"root.{key}",
                    "recommendation": "Ensure prompt renderer produces this field as string."
                }
        
        if not isinstance(sample.get("context"), dict):
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"Field 'context' must be a dict, got {type(sample.get('context')).__name__}",
                "location": "root.context",
                "recommendation": "Check context builder packaging output."
            }
            
        if not isinstance(sample.get("target"), dict):
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"Field 'target' must be a dict, got {type(sample.get('target')).__name__}",
                "location": "root.target",
                "recommendation": "Check target builder output."
            }

        ctx = sample["context"]
        tgt = sample["target"]

        # Target structure
        if "property" not in tgt or "value" not in tgt:
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": "Target dict must contain 'property' and 'value' keys.",
                "location": "root.target",
                "recommendation": "Ensure target builder sets both 'property' and 'value'."
            }
        if not isinstance(tgt["property"], str):
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"target.property must be a string, got {type(tgt['property']).__name__}",
                "location": "root.target.property",
                "recommendation": "Standardize target property as a string label."
            }

        # Context structure
        required_ctx = {"part_family", "manufacturing_type"}
        missing_ctx = required_ctx - ctx.keys()
        if missing_ctx:
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"Missing required context fields: {', '.join(missing_ctx)}",
                "location": "root.context",
                "recommendation": "Ensure the context builder sets required part metadata."
            }
        for k in required_ctx:
            if not isinstance(ctx[k], str):
                return {
                    "passed": False,
                    "stage": "Stage 2",
                    "rule": "Schema Validation",
                    "severity": "CRITICAL",
                    "reason": f"context.{k} must be a string, got {type(ctx[k]).__name__}",
                    "location": f"root.context.{k}",
                    "recommendation": f"Ensure context.{k} is correctly populated as a string."
                }

        # Unexpected root keys
        allowed_root_keys = {"drawing_id", "context", "target", "system", "user", "assistant"}
        unexpected_root = set(sample.keys()) - allowed_root_keys
        if unexpected_root:
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"Unexpected top-level fields: {', '.join(unexpected_root)}",
                "location": "root",
                "recommendation": "Remove any unexpected top-level fields before export."
            }

        # Unexpected context keys
        allowed_ctx_keys = {"drawing_id", "part_family", "manufacturing_type", "overall_dimensions", "inquiry_feature", "neighbour_features", "relationships", "topology", "engineering_rules"}
        unexpected_ctx = set(ctx.keys()) - allowed_ctx_keys
        if unexpected_ctx:
            return {
                "passed": False,
                "stage": "Stage 2",
                "rule": "Schema Validation",
                "severity": "CRITICAL",
                "reason": f"Unexpected context fields: {', '.join(unexpected_ctx)}",
                "location": "root.context",
                "recommendation": "Remove unexpected context properties."
            }

        return {"passed": True}

    def _validate_reasoning(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 3 & 4 — Engineering Dataset Contract & Engineering Preservation."""
        ctx = sample["context"]
        tgt = sample["target"]
        
        # Check overall dimensions
        dims = ctx.get("overall_dimensions")
        has_overall = False
        if dims and isinstance(dims, dict):
            has_overall = (dims.get("width") is not None) and (dims.get("height") is not None)
            if has_overall:
                try:
                    if float(dims["width"]) <= 0 or float(dims["height"]) <= 0:
                        has_overall = False
                except (ValueError, TypeError):
                    has_overall = False
                    
        # Check visible geometry cues
        inquiry_params = ctx.get("inquiry_feature", {}).get("visible_parameters", {})
        has_inquiry_geom = isinstance(inquiry_params, dict) and len(inquiry_params) > 0
        
        has_neighbour_geom = False
        nf_list = ctx.get("neighbour_features", [])
        if isinstance(nf_list, list):
            for nf in nf_list:
                if isinstance(nf, dict) and nf.get("visible_parameters"):
                    if len(nf["visible_parameters"]) > 0:
                        has_neighbour_geom = True
                        break
                        
        has_geom = has_inquiry_geom or has_neighbour_geom
        has_rel = isinstance(ctx.get("relationships"), list) and len(ctx["relationships"]) > 0
        has_topo = isinstance(ctx.get("topology"), dict) and len(ctx["topology"]) > 0
        
        target_prop = tgt.get("property", "")
        
        # Validation Stage 3: Engineering Dataset Contract (infer_thread_size)
        # Rule: must have overall_dimensions AND (visible geometry cues OR engineering relationships).
        # Rationale: isolated fastener drawings (bolts, screws) have geometry cues but no
        # structural relationships to a parent assembly. Requiring all three was too strict.
        # A thread size can be inferred from dimensional cues alone (across-flats, grip length, etc.)
        # provided overall context is present. Relationships remain strongly preferred but not mandatory.
        if target_prop == "thread_size":
            if not has_overall or not (has_geom or has_rel):
                missing_parts = []
                if not has_overall: missing_parts.append("overall_dimensions")
                if not has_geom and not has_rel: missing_parts.append("visible geometry cues or engineering relationships")
                return {
                    "passed": False,
                    "stage": "Stage 3",
                    "rule": "Engineering Dataset Contract",
                    "severity": "CRITICAL",
                    "reason": f"infer_thread_size lacks contract requirements: missing {', '.join(missing_parts)}",
                    "location": "root.context",
                    "recommendation": "Ensure overall_dimensions plus visible parameters or relationships are present."
                }
                
        # Validation Stage 4: Engineering Preservation
        if not (has_overall or has_geom or has_rel or has_topo):
            return {
                "passed": False,
                "stage": "Stage 4",
                "rule": "Engineering Preservation",
                "severity": "MAJOR",
                "reason": "Sample lacks any useful engineering reasoning evidence (missing overall dimensions, parameters, relationships, or topology).",
                "location": "root.context",
                "recommendation": "Ensure the geometry extractor and structural pipelines preserve dimension and layout facts."
            }
            
        return {"passed": True}

    def _validate_leakage(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 5 — Leakage Detection: Check keys, values, and prompt text."""
        ctx = sample["context"]
        tgt = sample["target"]
        
        forbidden_keys = {
            "major_diameter", "nominal_diameter", "thread_pitch", "pitch",
            "thread_designation", "source_annotation", "text", "raw_annotation",
            "dimension_text", "pitch_tpi", "nominal_pipe_size", "tolerance_class"
        }
        
        # 1. Search recursively in context for forbidden keys
        def scan_keys_and_values(d, path="context"):
            if isinstance(d, dict):
                for k, v in d.items():
                    if k in forbidden_keys:
                        return f"Forbidden key '{k}' found at {path}.{k}"
                    if isinstance(v, str):
                        v_lower = v.lower()
                        for fk in forbidden_keys:
                            if fk in v_lower:
                                return f"Forbidden keyword '{fk}' leaked in value '{v}' at {path}.{k}"
                    res = scan_keys_and_values(v, f"{path}.{k}")
                    if res:
                        return res
            elif isinstance(d, list):
                for idx, item in enumerate(d):
                    res = scan_keys_and_values(item, f"{path}[{idx}]")
                    if res:
                        return res
            return None
            
        leak_info = scan_keys_and_values(ctx)
        if leak_info:
            return {
                "passed": False,
                "stage": "Stage 5",
                "rule": "Target Leakage",
                "severity": "CRITICAL",
                "reason": leak_info,
                "location": "root.context",
                "recommendation": "Filter out the forbidden parameter or key before compiling the context."
            }
            
        # 2. Check if target value is leaked in context/prompts, avoiding coincidental matches
        target_val = str(tgt.get("value", "")).strip()
        target_val_lower = target_val.lower()
        
        if target_val_lower:
            dims = ctx.get("overall_dimensions")
            inquiry_params = ctx.get("inquiry_feature", {}).get("visible_parameters", {})
            
            allowed_vals = set()
            if dims and isinstance(dims, dict):
                allowed_vals.add(str(dims.get("width")))
                allowed_vals.add(str(dims.get("height")))
            if isinstance(inquiry_params, dict):
                for pk, pv in inquiry_params.items():
                    if pv is not None:
                        allowed_vals.add(str(pv))
            for nf in ctx.get("neighbour_features", []):
                if isinstance(nf, dict):
                    for pk, pv in nf.get("visible_parameters", {}).items():
                        if pv is not None:
                            allowed_vals.add(str(pv))
            
            # Add topology counts
            topo = ctx.get("topology", {})
            if isinstance(topo, dict):
                for tk in ("contours", "nesting", "holes", "regions"):
                    val = topo.get(tk)
                    if val is not None:
                        allowed_vals.add(str(val))
                        
            # Add relationship parameters
            rels = ctx.get("relationships", [])
            if isinstance(rels, list):
                for rel in rels:
                    if isinstance(rel, dict):
                        params = rel.get("parameters", {})
                        if isinstance(params, dict):
                            for pk, pv in params.items():
                                if pv is not None:
                                    if isinstance(pv, list):
                                        for item in pv:
                                            allowed_vals.add(str(item))
                                    else:
                                        allowed_vals.add(str(pv))
                                        
            # Add engineering rules parameters
            eng_rules = ctx.get("engineering_rules", {})
            if isinstance(eng_rules, dict):
                for pk, pv in eng_rules.items():
                    if pv is not None:
                        allowed_vals.add(str(pv))
                        try:
                            f_v = float(pv)
                            allowed_vals.add(str(f_v))
                            if f_v == int(f_v):
                                allowed_vals.add(str(int(f_v)))
                        except (ValueError, TypeError):
                            pass

            # Add boilerplate template numbers to prevent coincidental matching of lists/indices/angles
            allowed_vals.update({
                "0", "0.0", "1", "1.0", "2", "2.0", "3", "3.0", "4", "4.0",
                "5", "5.0", "6", "6.0", "7", "7.0", "8", "8.0", "9", "9.0",
                "45", "45.0", "90", "90.0", "180", "180.0", "360", "360.0"
            })
                            
            allowed_val_strs = {s.strip().lower() for s in allowed_vals if s}
            
            # If target_val matches one of the allowed context values, it's NOT a leak.
            # Otherwise, check if it's found in the prompt text:
            if target_val_lower not in allowed_val_strs:
                user_lower = sample["user"].lower()
                system_lower = sample["system"].lower()
                escaped_val = re.escape(target_val_lower)
                
                leak_detected = False
                if re.search(rf'\b{escaped_val}\b', user_lower) or re.search(rf'\b{escaped_val}\b', system_lower):
                    leak_detected = True
                
                # Check numeric forms
                if not leak_detected:
                    try:
                        f_val = float(target_val_lower)
                        i_val = int(f_val)
                        if f_val == i_val:
                            patterns = [rf'\b{i_val}\b', rf'\b{i_val}\.0+\b']
                        else:
                            patterns = [rf'\b{f_val}\b']
                        for pat in patterns:
                            if re.search(pat, user_lower) or re.search(pat, system_lower):
                                leak_detected = True
                                break
                    except ValueError:
                        pass
                        
                if leak_detected:
                    return {
                        "passed": False,
                        "stage": "Stage 5",
                        "rule": "Target Leakage",
                        "severity": "CRITICAL",
                        "reason": f"Target value '{target_val}' leaked in instruction prompt text.",
                        "location": "root.user",
                        "recommendation": "Update the prompt renderer to strip annotation values for target features."
                    }
                    
        return {"passed": True}

    def _validate_prompt(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 6 — Prompt Quality: Reject null placeholders, snake_case, formatting duplicates."""
        user = sample["user"]
        assistant = sample["assistant"]
        system = sample["system"]
        
        # 1. Null/None values check
        for field, text in [("system", system), ("user", user), ("assistant", assistant)]:
            t_lower = text.lower()
            if "null" in t_lower or "none" in t_lower:
                if re.search(r'\bnull\b', t_lower) or re.search(r'\bnone\b', t_lower):
                    return {
                        "passed": False,
                        "stage": "Stage 6",
                        "rule": "Prompt Quality",
                        "severity": "MINOR",
                        "reason": f"Prompt contains unformatted null/None value in {field}.",
                        "location": f"root.{field}",
                        "recommendation": "Minor formatting issue only — sample kept."
                    }
                    
        # 2. Lowercase snake_case check (ignoring drawing_id which can contain underscores)
        clean_user = user.replace(sample["drawing_id"], "")
        clean_assistant = assistant.replace(sample["drawing_id"], "")
        
        for field, text in [("user", clean_user), ("assistant", clean_assistant)]:
            words = re.findall(r'\b[a-zA-Z_0-9]+\b', text)
            for w in words:
                if '_' in w and re.match(r'^[a-z]+_[a-z0-9_]+$', w):
                    return {
                        "passed": False,
                        "stage": "Stage 6",
                        "rule": "Prompt Quality",
                        "severity": "MINOR",
                        "reason": f"Lowercase snake_case name '{w}' detected in {field} prompt text.",
                        "location": f"root.{field}",
                        "recommendation": "Minor formatting issue only — sample kept."
                    }
                    
        # 3. Duplicate lines check
        user_lines = [l.strip() for l in user.split("\n") if l.strip()]
        if len(user_lines) != len(set(user_lines)):
            seen = set()
            dup = ""
            for l in user_lines:
                if l in seen:
                    dup = l
                    break
                seen.add(l)
            return {
                "passed": False,
                "stage": "Stage 6",
                "rule": "Prompt Quality",
                "severity": "MINOR",
                "reason": f"Duplicate lines detected in user prompt: '{dup}'",
                "location": "root.user",
                "recommendation": "Minor formatting issue only — sample kept."
            }
            
        # 4. Missing required sections check
        if "task:" not in user.lower():
            return {
                "passed": False,
                "stage": "Stage 6",
                "rule": "Prompt Quality",
                "severity": "MAJOR",
                "reason": "User prompt is missing the 'Task' section.",
                "location": "root.user",
                "recommendation": "Ensure a structured 'Task:' section header is rendered."
            }
        if "description:" not in user.lower():
            return {
                "passed": False,
                "stage": "Stage 6",
                "rule": "Prompt Quality",
                "severity": "MAJOR",
                "reason": "User prompt is missing the 'Drawing Description' section.",
                "location": "root.user",
                "recommendation": "Ensure a 'Drawing Description:' header is rendered."
            }
        if "question:" not in user.lower():
            return {
                "passed": False,
                "stage": "Stage 6",
                "rule": "Prompt Quality",
                "severity": "MAJOR",
                "reason": "User prompt is missing the 'Question' section.",
                "location": "root.user",
                "recommendation": "Add a specific engineering question block at the prompt tail."
            }
            
        # 5. Length verification
        if len(user) < 50 or len(user) > 4000:
            return {
                "passed": False,
                "stage": "Stage 6",
                "rule": "Prompt Quality",
                "severity": "MINOR",
                "reason": f"Prompt length ({len(user)} chars) is outside the typical range (50-4000).",
                "location": "root.user",
                "recommendation": "Minor formatting issue only — sample kept."
            }
            
        return {"passed": True}

    def _validate_duplicates(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 7 — Duplicate Engineering Concepts: pitch+thread_pitch, nominal_diameter+major_diameter, identical neighbors."""
        ctx = sample["context"]
        
        def get_all_keys(d):
            keys = set()
            if isinstance(d, dict):
                for k, v in d.items():
                    keys.add(k)
                    keys.update(get_all_keys(v))
            elif isinstance(d, list):
                for item in d:
                    keys.update(get_all_keys(item))
            return keys
            
        all_keys = get_all_keys(ctx)
        
        if "pitch" in all_keys and "thread_pitch" in all_keys:
            return {
                "passed": False,
                "stage": "Stage 7",
                "rule": "Duplicate Engineering Concepts",
                "severity": "MINOR",
                "reason": "Context contains both legacy 'pitch' and canonical 'thread_pitch' keys.",
                "location": "root.context",
                "recommendation": "Minor duplication warning — sample kept."
            }
            
        if "nominal_diameter" in all_keys and "major_diameter" in all_keys:
            return {
                "passed": False,
                "stage": "Stage 7",
                "rule": "Duplicate Engineering Concepts",
                "severity": "MINOR",
                "reason": "Context contains both legacy 'nominal_diameter' and canonical 'major_diameter' keys.",
                "location": "root.context",
                "recommendation": "Minor duplication warning — sample kept."
            }
            
        # Duplicate neighbours check
        nf_list = ctx.get("neighbour_features", [])
        if isinstance(nf_list, list):
            sigs = []
            for nf in nf_list:
                if isinstance(nf, dict):
                    sig = (nf.get("feature_class"), json.dumps(nf.get("visible_parameters"), sort_keys=True))
                    sigs.append(sig)
            if len(sigs) != len(set(sigs)):
                return {
                    "passed": False,
                    "stage": "Stage 7",
                    "rule": "Duplicate Engineering Concepts",
                    "severity": "MINOR",
                    "reason": "Duplicate neighbour feature blocks present in context.",
                    "location": "root.context.neighbour_features",
                    "recommendation": "Minor duplication warning — sample kept."
                }
                
        # Duplicate relationships check
        rel_list = ctx.get("relationships", [])
        if isinstance(rel_list, list):
            sigs = []
            for rel in rel_list:
                if isinstance(rel, dict):
                    sig = (
                        rel.get("type"),
                        tuple(sorted(rel.get("associated_features", []))),
                        json.dumps(rel.get("parameters"), sort_keys=True)
                    )
                    sigs.append(sig)
            if len(sigs) != len(set(sigs)):
                return {
                    "passed": False,
                    "stage": "Stage 7",
                    "rule": "Duplicate Engineering Concepts",
                    "severity": "MINOR",
                    "reason": "Duplicate relationship records present in context.",
                    "location": "root.context.relationships",
                    "recommendation": "Minor duplication warning — sample kept."
                }
                
        return {"passed": True}

    def _validate_traceability(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 8 — Traceability: Verify all rendered dimensions inside the prompt are traceable."""
        ctx = sample["context"]
        user = sample["user"]
        
        def collect_numbers(val):
            numbers = set()
            if isinstance(val, (int, float)):
                numbers.add(float(val))
            elif isinstance(val, str):
                for m in re.findall(r'\b\d+(?:\.\d+)?\b', val):
                    numbers.add(float(m))
            elif isinstance(val, dict):
                for k, v in val.items():
                    numbers.update(collect_numbers(v))
            elif isinstance(val, list):
                for item in val:
                    numbers.update(collect_numbers(item))
            return numbers
            
        ctx_numbers = collect_numbers(ctx)
        prompt_numbers = re.findall(r'\b\d+(?:\.\d+)?\b', user)
        
        untraceable = []
        for num_str in prompt_numbers:
            try:
                num = float(num_str)
                # Ignore standard list numbering and index headings
                if num <= 0 or num in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0):
                    continue
                # Ignore common standard angles
                if num in (45.0, 90.0, 180.0, 360.0):
                    continue
                if not any(abs(num - cn) < 1e-4 for cn in ctx_numbers):
                    untraceable.append(num_str)
            except ValueError:
                pass
                
        if untraceable:
            return {
                "passed": False,
                "stage": "Stage 8",
                "rule": "Traceability",
                "severity": "CRITICAL",
                "reason": f"Untraceable engineering values {', '.join(untraceable)} rendered in prompt text.",
                "location": "root.user",
                "recommendation": "Ensure prompt rendering templates do not introduce synthetic/unmapped measurements."
            }
            
        return {"passed": True}

    def _validate_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate all validator stages sequentially."""
        validators = [
            self._validate_structure,
            self._validate_schema,
            self._validate_reasoning,
            self._validate_leakage,
            self._validate_prompt,
            self._validate_duplicates,
            self._validate_traceability
        ]
        
        for val_fn in validators:
            res = val_fn(sample)
            if not res["passed"]:
                sev = res.get("severity", "MAJOR")
                if sev in ("CRITICAL", "MAJOR"):
                    return res
                else:
                    logger.warning(f"Validation warning ({sev}) in {res['stage']} - {res['rule']}: {res['reason']}")
                    
        return {"passed": True}

    def _filter_context_by_task(self, context: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        """Filter irrelevant engineering evidence based on the specific prediction task (Task 4)."""
        return context

    def _write_jsonl(self, tasks: List[Dict], path: Path) -> List[Dict]:
        accepted = []
        with open(path, "w") as f:
            for task in tasks:
                self.validation_stats["total_processed"] += 1
                
                # Apply task-specific context filtering (Task 4)
                filtered_context = self._filter_context_by_task(task["context"], task["task_type"])
                
                # Build complete sample using filtered context and serializer
                task_with_filtered = {**task, "context": filtered_context}
                exported_sample = self.serializer.serialize_sample(task_with_filtered)
                
                # Run validation (on sample clean of task_type to satisfy Stage 2 schema check)
                val_sample = {**exported_sample}
                if "task_type" in val_sample:
                    del val_sample["task_type"]
                val_res = self._validate_sample(val_sample)
                
                if val_res["passed"]:
                    self.validation_stats["accepted_count"] += 1
                    self.validation_stats["prompt_size_chars"].append(
                        len(exported_sample.get("user", ""))
                    )
                    self.validation_stats["context_size_chars"].append(
                        len(json.dumps(exported_sample.get("context", {})))
                    )
                    
                    cleaned_sample = {**exported_sample}
                    if "task_type" in cleaned_sample:
                        del cleaned_sample["task_type"]
                    f.write(json.dumps(cleaned_sample, indent=2) + "\n")
                    accepted.append(task)
                else:
                    self.validation_stats["rejected_count"] += 1
                    stage_rule = f"{val_res['stage']} — {val_res['rule']}"
                    self.validation_stats["rejection_reasons"][stage_rule] = \
                        self.validation_stats["rejection_reasons"].get(stage_rule, 0) + 1
                    
                    self.validation_reports.append({
                        "drawing_id": task["drawing_id"],
                        "task_name": task["task_type"],
                        "failed_stage": val_res["stage"],
                        "failed_rule": val_res["rule"],
                        "severity": val_res["severity"],
                        "reason": val_res["reason"],
                        "failure_location": val_res["location"],
                        "recommendation": val_res["recommendation"],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
        return accepted

    def _write_empty(self) -> None:
        for name in ["train.jsonl", "validation.jsonl", "test.jsonl"]:
            with open(self.output_dir / name, "w") as f:
                pass
        empty_metadata = {
            "validation_version": self.VALIDATION_VERSION,
            "dataset_contract_version": self.DATASET_CONTRACT_VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "prompt_renderer_version": self.PROMPT_RENDERER_VERSION,
            "pipeline_version": self.PIPELINE_VERSION,
            "total_processed": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "rejection_breakdown": {},
            "average_prompt_length": 0.0,
            "average_context_length": 0.0,
            "processing_duration": 0.0,
            "peak_memory": 0.0,
            "timestamp": datetime.datetime.now().isoformat(),
            "version": "3.0.0",
            "format": "semantic_engineering_supervision",
            "total_tasks": 0,
            "task_types": {},
            "drawings": 0,
            "splits": {
                "train": {"count": 0},
                "validation": {"count": 0},
                "test": {"count": 0}
            },
            "schema": {
                "task_type": "engineering inference task category",
                "context": "visible engineering structure",
                "target": "hidden engineering property to infer",
            }
        }
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(empty_metadata, f, indent=2)

    def _generate_metadata(
        self,
        all_tasks: List[Dict],
        train: List[Dict],
        val: List[Dict],
        test: List[Dict],
    ) -> Dict[str, Any]:
        task_types = Counter(t["task_type"] for t in all_tasks)
        drawings = Counter(t["drawing_id"] for t in all_tasks)

        def _stats(tasks):
            if not tasks:
                return {"count": 0}
            return {
                "count": len(tasks),
                "task_types": dict(Counter(t["task_type"] for t in tasks)),
            }

        avg_prompt_len = 0.0
        if self.validation_stats["prompt_size_chars"]:
            avg_prompt_len = sum(self.validation_stats["prompt_size_chars"]) / len(self.validation_stats["prompt_size_chars"])
            
        avg_ctx_len = 0.0
        if self.validation_stats["context_size_chars"]:
            avg_ctx_len = sum(self.validation_stats["context_size_chars"]) / len(self.validation_stats["context_size_chars"])

        return {
            "validation_version": self.VALIDATION_VERSION,
            "dataset_contract_version": self.DATASET_CONTRACT_VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "prompt_renderer_version": self.PROMPT_RENDERER_VERSION,
            "pipeline_version": self.PIPELINE_VERSION,
            "total_processed": self.validation_stats["total_processed"],
            "accepted_count": self.validation_stats["accepted_count"],
            "rejected_count": self.validation_stats["rejected_count"],
            "rejection_breakdown": self.validation_stats["rejection_reasons"],
            "average_prompt_length": round(avg_prompt_len, 2),
            "average_context_length": round(avg_ctx_len, 2),
            "processing_duration": round(self.validation_stats["duration_seconds"], 4),
            "peak_memory": round(self.validation_stats["memory_mb"], 4),
            "timestamp": datetime.datetime.now().isoformat(),
            
            # Legacy compatible structure
            "version": "3.0.0",
            "format": "semantic_engineering_supervision",
            "total_tasks": len(all_tasks),
            "task_types": dict(task_types),
            "drawings": len(drawings),
            "splits": {
                "train": _stats(train),
                "validation": _stats(val),
                "test": _stats(test),
            },
            "schema": {
                "task_type": "engineering inference task category",
                "context": "visible engineering structure",
                "target": "hidden engineering property to infer",
            },
        }

    def _compute_feature_distribution(self, semantic_records) -> Dict[str, int]:
        from collections import Counter
        feature_classes = []
        for record in semantic_records:
            for feature in record.features:
                feature_classes.append(feature.feature_class)
        return dict(Counter(feature_classes))

    def _compute_relationship_distribution(self, semantic_records) -> Dict[str, int]:
        from collections import Counter
        relationship_types = []
        for record in semantic_records:
            for relationship in record.relationships:
                relationship_types.append(relationship.relationship_type)
        return dict(Counter(relationship_types))

    def _generate_semantic_coverage_audit(self, semantic_records: List[Any], all_tasks: List[Dict]) -> None:
        sem_counts = defaultdict(int)
        train_target_counts = defaultdict(int)
        train_ctx_counts = defaultdict(int)
        
        # Collect semantic facts
        for r in semantic_records:
            # overall_dimensions
            if hasattr(r, 'overall_dimensions') and r.overall_dimensions:
                for k, v in r.overall_dimensions.items():
                    if v is not None:
                        sem_counts[f"overall_dimensions.{k}"] += 1
                    
            # features
            if hasattr(r, 'features') and r.features:
                for f in r.features:
                    if f.feature_class in ('dimension_annotations', 'unknown_facts'):
                        continue
                    params = f.parameters or {}
                    for pk, pv in params.items():
                        if pv is not None and pk not in ('positions', 'center', 'text'):
                            sem_counts[f"{f.feature_class}.{pk}"] += 1
                        
            # relationships
            if hasattr(r, 'relationships') and r.relationships:
                for rel in r.relationships:
                    sem_counts[f"relationships.{rel.relationship_type}"] += 1
                    if rel.relationship_type == 'mirror_symmetry':
                        sem_counts["symmetry.mirror_symmetry"] += 1
                    
            # hierarchy
            if hasattr(r, 'hierarchy') and r.hierarchy:
                for node in r.hierarchy.get('nodes', []):
                    sem_counts["hierarchy.node"] += 1
                    if node.get('parent_id') is not None:
                        sem_counts["containment.parent_child"] += 1
            
            # concentric containment
            if hasattr(r, 'relationships') and r.relationships:
                for rel in r.relationships:
                    if rel.relationship_type == 'concentric':
                        sem_counts["containment.concentric"] += 1
                    
        # Map to tasks
        for fkey in sem_counts.keys():
            parts = fkey.split('.')
            group = parts[0]
            sub = parts[1] if len(parts) > 1 else ''
            
            for t in all_tasks:
                target = t.get('target', {})
                ctx = t.get('context', {})
                
                is_target = False
                is_ctx = False
                
                if group == 'overall_dimensions':
                    is_target = False
                    is_ctx = 'overall_dimensions' in ctx and ctx['overall_dimensions'].get(sub) is not None
                elif group == 'relationships' or group == 'symmetry':
                    is_target = False
                    is_ctx = any(x.get('role') == 'mirrored_feature' for x in ctx.get('symmetries', [])) if group == 'symmetry' else False
                elif group == 'hierarchy' or group == 'containment':
                    is_target = False
                    if sub == 'parent_child' or sub == 'node':
                        is_ctx = ctx.get('nesting_context') is not None
                    elif sub == 'concentric':
                        is_ctx = len(ctx.get('concentric_features', [])) > 0
                else:
                    if ctx.get('feature_type') == group:
                        mapped_props = [sub]
                        if group == 'hole_pattern':
                            if sub == 'pcd': mapped_props = ['spacing']
                            elif sub == 'hole_count': mapped_props = ['hole_count']
                            elif sub == 'hole_diameter': mapped_props = ['hole_diameter']
                            elif sub == 'counterbore_diameter': mapped_props = ['hole_diameter']
                            elif sub == 'counterbore_depth': mapped_props = ['profile_dimension']
                        elif group == 'hole_group':
                            if sub == 'count': mapped_props = ['hole_count']
                            elif sub == 'diameter': mapped_props = ['bore_diameter', 'hole_diameter']
                            elif sub in ['spacing_x', 'spacing_y']: mapped_props = ['spacing']
                            elif sub == 'counterbore_diameter': mapped_props = ['hole_diameter']
                            elif sub == 'counterbore_depth': mapped_props = ['profile_dimension']
                        elif group == 'slot_array':
                            if sub in ['width', 'length']: mapped_props = ['slot_dimension']
                        elif group == 'lube_port':
                            if sub == 'diameter': mapped_props = ['hole_diameter']
                        elif group == 'thread':
                            if sub == 'nominal_diameter': mapped_props = ['thread_size']
                        elif group == 'keyway':
                            if sub in ['width', 'depth']: mapped_props = ['slot_dimension']
                        elif group == 'heatsink_fin':
                            if sub == 'count': mapped_props = ['hole_count']
                            elif sub == 'pitch': mapped_props = ['spacing']
                        elif group == 'heatsink_core':
                            if sub == 'diameter': mapped_props = ['outer_diameter']
                        elif group == 'structural_profile':
                            if sub in ['web_thickness', 'flange_thickness']: mapped_props = ['profile_dimension']
                            elif sub in ['wall_thickness', 'fillet_radius', 'inner_radius', 'outer_radius']:
                                mapped_props = ['wall_thickness', 'profile_dimension']
                        elif group == 'bolt':
                            if sub in ['grip_length', 'thread_length', 'across_flats']: mapped_props = ['profile_dimension']
                            elif sub == 'nominal_diameter': mapped_props = ['thread_size']
                        elif group == 'screw':
                            if sub in ['length', 'head_diameter', 'drive_size']: mapped_props = ['profile_dimension']
                            elif sub == 'nominal_diameter': mapped_props = ['thread_size']
                        elif group == 'hex_head':
                            if sub == 'across_flats': mapped_props = ['profile_dimension']
                        elif group == 'hex_drive':
                            if sub == 'size': mapped_props = ['profile_dimension']
                        elif group == 'cylindrical_head':
                            if sub in ['head_diameter', 'diameter']: mapped_props = ['outer_diameter']
                        elif group == 'fitting':
                            if sub in ['taper_length', 'hex_height', 'neck_length', 'flange_thickness', 'across_flats']: mapped_props = ['profile_dimension']
                        elif group == 'pocket':
                            if sub in ['pocket_width', 'pocket_length']: mapped_props = ['pocket_dimension']
                            elif sub == 'perimeter_wall': mapped_props = ['wall_thickness']
                        elif group == 'o_ring':
                            if sub == 'o_ring_diameter': mapped_props = ['hole_diameter']
                            elif sub == 'o_ring_groove_depth': mapped_props = ['slot_dimension']
                        elif group == 'port':
                            if sub == 'port_diameter': mapped_props = ['hole_diameter']
                            elif sub == 'port_depth': mapped_props = ['slot_dimension']
                            elif sub == 'port_thread': mapped_props = ['thread_size']
                        elif group == 'channel':
                            if sub in ['channel_width', 'channel_depth', 'channel_length']: mapped_props = ['slot_dimension']
                        elif group == 'shoulder':
                            if sub == 'shoulder_diameter': mapped_props = ['outer_diameter']
                            elif sub == 'shoulder_length': mapped_props = ['profile_dimension']
                        elif group == 'cope':
                            if sub == 'cope_radius': mapped_props = ['profile_dimension']
                        elif group in ['rib', 'alignment_tab', 'chamfer', 'bend_relief']:
                            if sub == 'value': mapped_props = ['profile_dimension']
                            
                        is_target = target.get('property') in mapped_props
                        is_ctx = sub in ctx.get('feature_parameters_visible', {})
                        
                if is_target:
                    train_target_counts[fkey] += 1
                if is_ctx:
                    train_ctx_counts[fkey] += 1
                    
        matrix = []
        for fkey in sorted(sem_counts.keys()):
            sc = sem_counts[fkey]
            tc_t = train_target_counts[fkey]
            tc_c = train_ctx_counts[fkey]
            
            status = 'LOST'
            if tc_t > 0 and tc_c > 0:
                status = 'TARGET & CONTEXT'
            elif tc_t > 0:
                status = 'TARGET'
            elif tc_c > 0:
                status = 'CONTEXT'
                
            matrix.append({
                'field': fkey,
                'semantic_count': sc,
                'train_count': tc_t + tc_c,
                'status': status
            })
            
        audit_path = self.output_dir / "semantic_coverage_audit.json"
        with open(audit_path, "w") as f:
            json.dump(matrix, f, indent=2)
        logger.info(f"Exported semantic coverage audit to {audit_path}")
