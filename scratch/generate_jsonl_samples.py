import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.topology_pipeline import TopologyPipeline
from pipeline.structural_pipeline import StructuralPipeline
from pipeline.feature_pipeline import FeaturePipeline
from pipeline.refinement_pipeline import RefinementPipeline
from pipeline.context_pipeline import ContextPipeline
from pipeline.semantic_pipeline import SemanticPipeline, SemanticRecord, FeatureInstance
from pipeline.dataset_pipeline import DatasetExporter

DRAWINGS = [
    "Hardware_HW01_HexBolt.dxf",
    "Hardware_HW02_SHCS.dxf",
    "Hardware_HW04_ShoulderScrew.dxf",
    "Hardware_HW05_HexNut.dxf",
    "Fluid_PF02_HexBushing.dxf",
    "Fluid_PF05_HoseBarb.dxf",
    "Electrical_BB01_PhaseBusbar.dxf",
    "Bearing_Housing_BH01.dxf",
    "Circular_Flange_FL01.dxf",
    "Structural_ST01_IBeam.dxf",
    "Turned_Shaft_TS01.dxf"
]

def generate_samples():
    exporter = DatasetExporter(Path("data/intermediate"))
    all_tasks = []
    
    for dxf_name in DRAWINGS:
        dxf_path = Path("data/raw_dxf") / dxf_name
        if not dxf_path.exists():
            print(f"Skipping {dxf_name}: not found")
            continue
            
        print(f"Analyzing {dxf_name}...")
        try:
            extraction_result = ExtractionPipeline(str(dxf_path)).run()
            kept_entities = extraction_result["kept_entities"] if "kept_entities" in extraction_result else extraction_result["entities"]
            topology_result = TopologyPipeline().run(kept_entities)
            structural_result = StructuralPipeline().run(kept_entities, topology_result)
            feature_result = FeaturePipeline().run(kept_entities, structural_result)
            refinement_result = RefinementPipeline().run(feature_result)
            context_result = ContextPipeline().run(feature_result, refinement_result)
            
            pipeline_result = {
                "drawing_id": dxf_path.stem,
                "entities": kept_entities,
                "structural_result": structural_result,
                "feature_result": feature_result,
                "refinement_result": refinement_result,
                "context_result": context_result
            }
            
            record_dict = SemanticPipeline().run(pipeline_result)
            
            features = [
                FeatureInstance(
                    feature_id=f["feature_id"],
                    feature_class=f["feature_class"],
                    parameters=f["parameters"]
                ) for f in record_dict["features"]
            ]
            
            semantic_record = SemanticRecord(
                drawing_id=record_dict["drawing_id"],
                part_type=record_dict["part_type"],
                overall_dimensions=record_dict["overall_dimensions"],
                features=features,
                relationships=[]
            )
            
            tasks = exporter._build_tasks_from_semantic(semantic_record, pipeline_result)
            all_tasks.extend(tasks)
        except Exception as e:
            print(f"Error processing {dxf_name}: {e}")
            
    print(f"\nTotal tasks built: {len(all_tasks)}")
    
    # Print the JSONL preview for the first 15 tasks
    print("\n--- JSONL PREVIEW (Sample Records) ---")
    for i, t in enumerate(all_tasks[:15]):
        prompt_fields = exporter._build_instruction_prompt(
            t["task_type"],
            t["drawing_id"],
            t["context"],
            t["target"]
        )
        sample = {**t, **prompt_fields}
        if "task_type" in sample:
            del sample["task_type"]
        print(f"\n[SAMPLE {i+1}]")
        print(json.dumps(sample, indent=2))

if __name__ == "__main__":
    generate_samples()
