import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any
from core.reasoning.missing_dimension import MissingDimensionGenerator
from pipeline.split_policy import TRAIN_RATIO, VAL_RATIO
from utils.logger import get_logger

logger = get_logger(__name__)

class ReasoningPipeline:
    """
    Orchestrates the Stage 3 reasoning dataset generation.
    Consumes Version 2.0 baseline outputs and extends them with missing dimension tasks.
    """
    def __init__(self, run_dir: str):
        self.run_dir = Path(run_dir)
        self.export_dir = self.run_dir / "phase7_export"
        self.reasoning_dir = self.run_dir / "phase8_reasoning"
        self.reasoning_dir.mkdir(parents=True, exist_ok=True)
        
        self.generator = MissingDimensionGenerator()

    def run(self) -> Dict[str, Any]:
        logger.info("Starting Stage 3 Reasoning Pipeline")
        
        # 1. Load semantic records
        records_path = self.export_dir / "semantic_records.json"
        if not records_path.exists():
            logger.error(f"Semantic records file not found at {records_path}")
            return {"status": "FAILED", "reason": "No semantic records found"}
            
        with open(records_path) as f:
            semantic_records = json.load(f)
            
        logger.info(f"Loaded {len(semantic_records)} semantic records")
        
        # 2. Build map of drawing results
        result_map = {}
        for r in semantic_records:
            d_id = r["drawing_id"]
            # Load intermediate results
            result_map[d_id] = {
                "drawing_id": d_id,
                "structural_result": self._load_intermediate(d_id, "phase3_structural", "_structural"),
                "feature_result": self._load_intermediate(d_id, "phase4_features", "_features"),
                "refinement_result": self._load_intermediate(d_id, "phase5_refinement", "_refinement"),
                "context_result": self._load_intermediate(d_id, "phase6_context", "_context"),
                "entities": self._load_entities(d_id),
            }

        # 3. Generate missing dimension tasks
        all_new_tasks = []
        for record in semantic_records:
            d_id = record["drawing_id"]
            res = result_map.get(d_id)
            if res:
                tasks = self.generator.generate(record, res)
                all_new_tasks.extend(tasks)
                
        logger.info(f"Generated {len(all_new_tasks)} new missing dimension tasks")
        
        # 4. Partition and merge into splits
        splits = ["train", "validation", "test"]
        merged_metadata = {}
        baseline_split_by_drawing = self._baseline_split_map(splits)
        
        for split in splits:
            # Read V2.0 tasks
            v2_tasks = self._read_jsonl(self.export_dir / f"{split}.jsonl" if split != "validation" else self.export_dir / "validation.jsonl")
            
            # Filter new tasks belonging to this split
            new_split_tasks = [
                t for t in all_new_tasks
                if baseline_split_by_drawing.get(t["drawing_id"], self._assign_split(t["drawing_id"])) == split
            ]
            
            # Combine tasks
            combined_tasks = v2_tasks + new_split_tasks
            
            # Write to Stage 3 output
            output_name = "validation.jsonl" if split == "validation" else f"{split}.jsonl"
            self._write_jsonl(combined_tasks, self.reasoning_dir / output_name)
            
            merged_metadata[split] = {
                "v2_count": len(v2_tasks),
                "reasoning_count": len(new_split_tasks),
                "total_count": len(combined_tasks)
            }
            logger.info(f"Split {split} complete: v2={len(v2_tasks)} reasoning={len(new_split_tasks)}")

        # Write metadata
        with open(self.reasoning_dir / "metadata.json", "w") as f:
            json.dump({
                "status": "SUCCESS",
                "run_id": self.run_dir.name,
                "splits": merged_metadata,
                "total_reasoning_tasks": len(all_new_tasks)
            }, f, indent=2)

        return {"status": "SUCCESS", "metadata": merged_metadata}

    def _load_intermediate(self, d_id: str, phase_dir: str, suffix: str) -> Dict[str, Any]:
        path = self.run_dir / phase_dir / f"{d_id}{suffix}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def _load_entities(self, d_id: str) -> List[Dict[str, Any]]:
        path = self.run_dir / "phase1_extraction" / f"{d_id}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return data.get("entities", [])
        return []

    def _read_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        tasks = []
        if path.exists():
            with open(path) as f:
                for line in f:
                    if line.strip():
                        tasks.append(json.loads(line))
        return tasks

    def _write_jsonl(self, tasks: List[Dict[str, Any]], path: Path):
        with open(path, "w") as f:
            for task in tasks:
                f.write(json.dumps(task) + "\n")

    def _assign_split(self, drawing_id: str) -> str:
        """Assign an unseen drawing with the frozen baseline split policy."""
        cleaned = drawing_id.replace("Corrected_", "")
        cleaned = re.sub(r"_(variant|stress|step|v\d+|\d+mm)$", "", cleaned, flags=re.IGNORECASE)
        base_id = cleaned
        
        salt = "cad_engine_v2_split_salt"
        hash_input = f"{salt}_{base_id}".encode("utf-8")
        h = int(hashlib.md5(hash_input).hexdigest(), 16) % 100
        
        if h < int(TRAIN_RATIO * 100):
            return "train"
        elif h < int((TRAIN_RATIO + VAL_RATIO) * 100):
            return "validation"
        else:
            return "test"

    def _baseline_split_map(self, splits: List[str]) -> Dict[str, str]:
        """Preserve a drawing's existing V2.0 split when extending its tasks."""
        split_by_drawing: Dict[str, str] = {}
        for split in splits:
            for task in self._read_jsonl(self.export_dir / f"{split}.jsonl"):
                drawing_id = task.get("drawing_id")
                if not drawing_id:
                    continue
                existing = split_by_drawing.setdefault(drawing_id, split)
                if existing != split:
                    raise ValueError(
                        f"Frozen baseline split conflict for drawing {drawing_id}: "
                        f"{existing} and {split}"
                    )
        return split_by_drawing
