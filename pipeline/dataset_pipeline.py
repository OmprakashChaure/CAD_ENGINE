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
from pipeline.semantic_pipeline import SemanticPipeline, reconstruct_dimensions, extract_engineering_rules, normalize_thread_size
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

    Each drawing maps to exactly one canonical engineering record.
    """
    VALIDATION_VERSION = "3.0.0"
    DATASET_CONTRACT_VERSION = "3.0.0"
    SCHEMA_VERSION = "3.0.0"
    PROMPT_RENDERER_VERSION = "3.0.0"
    PIPELINE_VERSION = "3.0.0"

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.semantic_pipeline = SemanticPipeline()

    def export(
        self,
        all_pipeline_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build and export canonical engineering records for all drawings.
        """
        logger.info(
            f"DatasetExporter: processing {len(all_pipeline_results)} drawings"
        )

        semantic_records = []
        for result in all_pipeline_results:
            drawing_id = result.get("drawing_id", "unknown")
            try:
                # Call SemanticPipeline.run to get the SemanticRecord dict
                semantic_record_dict = self.semantic_pipeline.run(result)
                
                # Reconstruct semantic record object for split/topology logic
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
                
                semantic_records.append((semantic_record, result))
                
            except Exception as e:
                logger.error(f"Failed to build semantic record for {drawing_id}: {e}")
                continue

        logger.info(f"DatasetExporter: built {len(semantic_records)} semantic records")

        # Step 2: Export semantic records and metadata for diagnostic/legacy reasons
        if semantic_records:
            semantic_records_path = self.output_dir / "semantic_records.json"
            with open(semantic_records_path, "w") as f:
                json.dump(
                    [r[0].to_dict() for r in semantic_records],
                    f,
                    indent=2
                )
            logger.info(f"Exported semantic records to {semantic_records_path}")

            # Export semantic metadata
            semantic_metadata = {
                "total_drawings": len(semantic_records),
                "total_features": sum(len(r[0].features) for r in semantic_records),
                "total_relationships": sum(len(r[0].relationships) for r in semantic_records),
                "feature_class_distribution": self._compute_feature_distribution([r[0] for r in semantic_records]),
                "relationship_type_distribution": self._compute_relationship_distribution([r[0] for r in semantic_records])
            }
            semantic_metadata_path = self.output_dir / "semantic_metadata.json"
            with open(semantic_metadata_path, "w") as f:
                json.dump(semantic_metadata, f, indent=2)
            logger.info(f"Exported semantic metadata to {semantic_metadata_path}")
        else:
            logger.warning("No semantic records generated")

        # Step 3: Build Canonical Engineering Records
        all_records: List[Dict] = []
        for semantic_record, result in semantic_records:
            record = self._build_canonical_record(semantic_record, result)
            all_records.append(record)

        logger.info(f"DatasetExporter: generated {len(all_records)} canonical engineering records")

        if not all_records:
            logger.warning("No engineering records generated — check pipeline outputs")
            self._write_empty()
            return {
                "total_records": 0,
                "total_semantic_records": len(semantic_records)
            }

        # Deterministic split (each drawing goes entirely to one partition)
        train, val, test = self._split_deterministic(all_records)

        # Initialize validation stats and reports
        import time
        start_time = time.time()
        
        self.validation_reports = []
        self.validation_stats = {
            "total_processed": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "rejection_reasons": {},
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

        # Export metadata
        metadata = self._generate_metadata(all_records, train_accepted, val_accepted, test_accepted)
        metadata["total_semantic_records"] = len(semantic_records)
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            f"DatasetExporter: train={len(train_accepted)} (rejected={len(train) - len(train_accepted)}) "
            f"val={len(val_accepted)} (rejected={len(val) - len(val_accepted)}) "
            f"test={len(test_accepted)} (rejected={len(test) - len(test_accepted)})"
        )

        return metadata

    def _build_canonical_record(self, semantic_record: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        drawing_id = semantic_record.drawing_id
        
        # 1. Part Family
        parts = drawing_id.split("_")
        part_family = parts[0] if parts else "General"
        
        # 2. Manufacturing Type
        manufacturing_type = "machined"
        drawing_id_lower = drawing_id.lower()
        if any(k in drawing_id_lower for k in ("snapfit", "screwboss", "shelledbox", "livinghinge", "crushribs", "plastic", "_pl0")):
            manufacturing_type = "injection_moulded"
        elif "bolt" in drawing_id_lower or "shaft" in drawing_id_lower or "screw" in drawing_id_lower or "nut" in drawing_id_lower:
            manufacturing_type = "turned"
        elif "sheet" in drawing_id_lower or "bracket" in drawing_id_lower or "clip" in drawing_id_lower:
            manufacturing_type = "sheet_metal"
        elif "structural" in drawing_id_lower or "beam" in drawing_id_lower or "channel" in drawing_id_lower:
            manufacturing_type = "structural"
            
        # 3. Topology
        topology = {}
        struct_hierarchy = result.get("structural_result", {}).get("contour_hierarchy", {}).get("hierarchy", [])
        if struct_hierarchy:
            topology["contours"] = len(struct_hierarchy)
            topology["nesting"] = max([n.get("nesting_depth", 0) for n in struct_hierarchy])
        elif semantic_record.hierarchy:
            nodes = semantic_record.hierarchy.get("nodes", [])
            topology["contours"] = len(nodes)
            topology["nesting"] = max([n.get("nesting_depth", 0) for n in nodes]) if nodes else 0
        else:
            topology["contours"] = 0
            topology["nesting"] = 0

        feat_stats = result.get("feature_result", {}).get("statistics", {})
        topology["holes"] = feat_stats.get("holes", {}).get("total_candidates", 0)
        topology["regions"] = len(result.get("structural_result", {}).get("regions", []))
        
        # 4. Features & Relationships
        features = [
            f.to_dict() for f in semantic_record.features
            if f.feature_class not in ("dimension_annotations", "unknown_facts")
        ]
        relationships = [r.to_dict() for r in semantic_record.relationships]
        
        # 5. Annotations
        annotations = []
        for ent in result.get("entities", []):
            if ent.get("entity_type") in ("TEXT", "MTEXT"):
                geom = ent.get("geometry", {})
                text = geom.get("text") or geom.get("content") or ""
                if text:
                    annotations.append({
                        "handle": ent.get("handle"),
                        "text": text,
                        "position": geom.get("insert") or geom.get("position")
                    })
                    
        # 6. Dimension Entities
        dimension_entities = []
        for ent in result.get("entities", []):
            if ent.get("entity_type") == "DIMENSION":
                geom = ent.get("geometry", {})
                text = geom.get("text") or geom.get("content") or ""
                dimension_entities.append({
                    "handle": ent.get("handle"),
                    "text": text,
                    "value": geom.get("value") or geom.get("text_value"),
                    "dimension_type": geom.get("dimtype") or geom.get("dimension_type"),
                    "points": geom.get("points")
                })
                
        # 7. Engineering Constraints
        constraints_dict = extract_engineering_rules(result.get("entities", []))
        engineering_constraints = []
        for k, v in constraints_dict.items():
            engineering_constraints.append({
                "type": k,
                "value": v
            })
            
        # 8. Metadata
        metadata = {
            "feature_count": len(semantic_record.features),
            "relationship_count": len(semantic_record.relationships),
            "has_hierarchy": semantic_record.hierarchy is not None
        }
        
        # Assemble
        record = {
            "drawing_id": drawing_id,
            "part_family": part_family,
            "manufacturing_type": manufacturing_type,
            "overall_dimensions": semantic_record.overall_dimensions,
            "topology": topology,
            "features": features,
            "relationships": relationships,
            "annotations": annotations,
            "dimension_entities": dimension_entities,
            "engineering_constraints": engineering_constraints,
            "metadata": metadata
        }
        
        # Sanitize internal pipeline IDs
        record = self._remove_internal_pipeline_ids(record)
        return record

    def _remove_internal_pipeline_ids(self, obj: Any) -> Any:
        # Define keys that represent internal pipeline implementation details to strip
        internal_keys = {
            "candidate_id", "entity_id", "entity_ids", "group_id", 
            "member_candidate_ids", "candidate_ids", "parent_id", 
            "children_ids", "pattern_id", "member_ids"
        }
        
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in internal_keys:
                    continue
                cleaned[k] = self._remove_internal_pipeline_ids(v)
            return cleaned
        elif isinstance(obj, list):
            cleaned = []
            for item in obj:
                if isinstance(item, str):
                    if (
                        re.match(r'^(hc|rp|sc|cg|rg|ent|conc|sc)_\\w+$', item, re.IGNORECASE) or
                        item.startswith("hc_") or item.startswith("rp_") or item.startswith("sc_") or
                        item.startswith("cg_") or item.startswith("rg_") or item.startswith("ent_")
                    ):
                        continue
                cleaned.append(self._remove_internal_pipeline_ids(item))
            return cleaned
        elif isinstance(obj, str):
            if (
                re.match(r'^(hc|rp|sc|cg|rg|ent|conc|sc)_\\w+$', obj, re.IGNORECASE) or
                obj.startswith("hc_") or obj.startswith("rp_") or obj.startswith("sc_") or
                obj.startswith("cg_") or obj.startswith("rg_") or obj.startswith("ent_")
            ):
                return None
            return obj
        else:
            return obj

    def _split_deterministic(self, records: List[Dict]) -> tuple:
        def get_base_drawing_id(drawing_id: str) -> str:
            cleaned = drawing_id.replace("Corrected_", "")
            cleaned = re.sub(r"_(variant|stress|step|v\\d+|\\d+mm)$", "", cleaned, flags=re.IGNORECASE)
            return cleaned
            
        unique_base_ids = sorted(list(set(get_base_drawing_id(r["drawing_id"]) for r in records)))
        
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
        for r in records:
            base_id = get_base_drawing_id(r["drawing_id"])
            assignment = base_id_assignments.get(base_id, "train")
            
            if assignment == "train":
                train.append(r)
            elif assignment == "validation":
                val.append(r)
            else:
                test.append(r)
                
        train_drawings = set(t["drawing_id"] for t in train)
        val_drawings = set(t["drawing_id"] for t in val)
        test_drawings = set(t["drawing_id"] for t in test)
        
        overlap_train_val = train_drawings.intersection(val_drawings)
        overlap_train_test = train_drawings.intersection(test_drawings)
        overlap_val_test = val_drawings.intersection(test_drawings)
        
        if overlap_train_val or overlap_train_test or overlap_val_test:
            raise AssertionError(
                f"CRITICAL OVERLAP ERROR: Drawing splits are not isolated!\\n"
                f"  train & validation: {overlap_train_val}\\n"
                f"  train & test: {overlap_train_test}\\n"
                f"  validation & test: {overlap_val_test}"
            )
            
        logger.info(f"Split verification PASSED. Overlaps: train-val=0, train-test=0, val-test=0")
        
        return train, val, test

    def _validate_sample(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Validate engineering integrity and structure of canonical record."""
        if not record.get("drawing_id") or not isinstance(record["drawing_id"], str):
            return {
                "passed": False,
                "stage": "Structural",
                "rule": "DrawingID",
                "severity": "CRITICAL",
                "reason": "drawing_id is missing or not a string",
                "location": "root.drawing_id",
                "recommendation": "Ensure drawing_id is correctly mapped."
            }

        mandatory_keys = {
            "part_family", "manufacturing_type", "overall_dimensions",
            "topology", "features", "relationships", "annotations",
            "dimension_entities", "engineering_constraints", "metadata"
        }
        missing = mandatory_keys - record.keys()
        if missing:
            return {
                "passed": False,
                "stage": "Structural",
                "rule": "MandatoryFields",
                "severity": "CRITICAL",
                "reason": f"Missing mandatory fields: {', '.join(missing)}",
                "location": "root",
                "recommendation": "Ensure record builder populates all required architectural sections."
            }

        if not isinstance(record["features"], list):
            return {
                "passed": False,
                "stage": "Schema",
                "rule": "FeaturesType",
                "severity": "CRITICAL",
                "reason": "features must be a list",
                "location": "root.features",
                "recommendation": "Verify feature mapping outputs."
            }
        if not isinstance(record["relationships"], list):
            return {
                "passed": False,
                "stage": "Schema",
                "rule": "RelationshipsType",
                "severity": "CRITICAL",
                "reason": "relationships must be a list",
                "location": "root.relationships",
                "recommendation": "Verify relationship mapping outputs."
            }

        internal_keys = {
            "candidate_id", "entity_id", "entity_ids", "group_id", 
            "member_candidate_ids", "candidate_ids", "parent_id", 
            "children_ids", "pattern_id", "member_ids"
        }
        
        def check_leaked_ids(obj: Any) -> list:
            leaks = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in internal_keys:
                        leaks.append(k)
                    leaks.extend(check_leaked_ids(v))
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str):
                        if (
                            item.startswith("hc_") or item.startswith("ent_") or
                            item.startswith("sc_") or item.startswith("cg_")
                        ):
                            leaks.append(item)
                    leaks.extend(check_leaked_ids(item))
            return leaks

        leaks = check_leaked_ids(record)
        if leaks:
            return {
                "passed": False,
                "stage": "Leakage",
                "rule": "PipelineIDs",
                "severity": "CRITICAL",
                "reason": f"Internal pipeline IDs leaked: {', '.join(leaks)}",
                "location": "root",
                "recommendation": "Verify _remove_internal_pipeline_ids successfully sanitizes all record values."
            }

        try:
            json.dumps(record)
        except Exception as e:
            return {
                "passed": False,
                "stage": "Serialization",
                "rule": "JSONSerializable",
                "severity": "CRITICAL",
                "reason": f"Object not JSON serializable: {e}",
                "location": "root",
                "recommendation": "Ensure no un-serializable types are included in the record."
            }

        return {"passed": True}

    def _write_jsonl(self, records: List[Dict], path: Path) -> List[Dict]:
        accepted = []
        cleaned_records = []
        with open(path, "w") as f:
            for record in records:
                self.validation_stats["total_processed"] += 1
                val_res = self._validate_sample(record)
                
                if val_res["passed"]:
                    self.validation_stats["accepted_count"] += 1
                    f.write(json.dumps(record) + "\n")
                    cleaned_records.append(record)
                    accepted.append(record)
                else:
                    self.validation_stats["rejected_count"] += 1
                    stage_rule = f"{val_res['stage']} — {val_res['rule']}"
                    self.validation_stats["rejection_reasons"][stage_rule] = \
                        self.validation_stats["rejection_reasons"].get(stage_rule, 0) + 1
                    
                    self.validation_reports.append({
                        "drawing_id": record["drawing_id"],
                        "failed_stage": val_res["stage"],
                        "failed_rule": val_res["rule"],
                        "severity": val_res["severity"],
                        "reason": val_res["reason"],
                        "failure_location": val_res["location"],
                        "recommendation": val_res["recommendation"],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
        
        # Write pretty-printed JSON version
        if path.suffix == ".jsonl":
            pretty_path = path.with_name(path.stem + "_pretty.json")
        else:
            pretty_path = path.with_name(path.stem + "_pretty" + path.suffix)
        with open(pretty_path, "w") as pf:
            json.dump(cleaned_records, pf, indent=4)

        return accepted

    def _write_empty(self) -> None:
        for name in ["train.jsonl", "validation.jsonl", "test.jsonl"]:
            with open(self.output_dir / name, "w") as f:
                pass
        for name in ["train_pretty.json", "validation_pretty.json", "test_pretty.json"]:
            with open(self.output_dir / name, "w") as f:
                json.dump([], f, indent=4)
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
            "format": "canonical_engineering_representation",
            "total_records": 0,
            "drawings": 0,
            "splits": {
                "train": {"count": 0},
                "validation": {"count": 0},
                "test": {"count": 0}
            }
        }
        with open(self.output_dir / "metadata.json", "w") as f:
            json.dump(empty_metadata, f, indent=2)

    def _generate_metadata(
        self,
        all_records: List[Dict],
        train: List[Dict],
        val: List[Dict],
        test: List[Dict],
    ) -> Dict[str, Any]:
        drawings = Counter(r["drawing_id"] for r in all_records)

        def _stats(records):
            if not records:
                return {"count": 0}
            return {
                "count": len(records),
            }

        return {
            "validation_version": self.VALIDATION_VERSION,
            "dataset_contract_version": self.DATASET_CONTRACT_VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "pipeline_version": self.PIPELINE_VERSION,
            "total_processed": self.validation_stats["total_processed"],
            "accepted_count": self.validation_stats["accepted_count"],
            "rejected_count": self.validation_stats["rejected_count"],
            "rejection_breakdown": self.validation_stats["rejection_reasons"],
            "processing_duration": round(self.validation_stats["duration_seconds"], 4),
            "peak_memory": round(self.validation_stats["memory_mb"], 4),
            "timestamp": datetime.datetime.now().isoformat(),
            
            "version": "3.0.0",
            "format": "canonical_engineering_representation",
            "total_records": len(all_records),
            "drawings": len(drawings),
            "splits": {
                "train": _stats(train),
                "validation": _stats(val),
                "test": _stats(test),
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
