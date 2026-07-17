import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from pipeline.dataset_pipeline import DatasetPipeline, DatasetExporter
from pipeline.semantic_pipeline import SemanticPipeline, SemanticRecord, FeatureInstance

if __name__ == "__main__":
    try:
        # Process hex bolt to get pipeline result
        dxf_path = Path("data/raw_dxf/Hardware_HW01_HexBolt.dxf")
        from pipeline.extraction_pipeline import ExtractionPipeline
        from pipeline.topology_pipeline import TopologyPipeline
        from pipeline.structural_pipeline import StructuralPipeline
        from pipeline.feature_pipeline import FeaturePipeline
        from pipeline.refinement_pipeline import RefinementPipeline
        from pipeline.context_pipeline import ContextPipeline

        extraction_result = ExtractionPipeline(str(dxf_path)).run()
        kept_entities = (
            extraction_result["kept_entities"]
            if "kept_entities" in extraction_result
            else extraction_result["entities"]
        )

        topology_result = TopologyPipeline().run(kept_entities)
        structural_result = StructuralPipeline().run(kept_entities, topology_result)
        feature_result = FeaturePipeline().run(kept_entities, structural_result)
        refinement_result = RefinementPipeline().run(feature_result)
        context_result = ContextPipeline().run(
            feature_result, refinement_result
        )

        pipeline_result = {
            "drawing_id": dxf_path.stem,
            "entities": kept_entities,
            "structural_result": structural_result,
            "feature_result": feature_result,
            "refinement_result": refinement_result,
            "context_result": context_result,
        }

        # Build semantic record dictionary
        sem_pipeline = SemanticPipeline()
        record_dict = sem_pipeline.run(pipeline_result)

        # Convert back to SemanticRecord object for exporter
        features = [
            FeatureInstance(
                feature_id=f["feature_id"],
                feature_class=f["feature_class"],
                parameters=f["parameters"],
            )
            for f in record_dict["features"]
        ]
        semantic_record = SemanticRecord(
            drawing_id=record_dict["drawing_id"],
            part_type=record_dict["part_type"],
            overall_dimensions=record_dict["overall_dimensions"],
            features=features,
            relationships=[],
        )

        # Build tasks
        exporter_inst = DatasetExporter(Path("data/intermediate"))
        tasks = exporter_inst._build_tasks_from_semantic(
            semantic_record, pipeline_result
        )

        print(f"Generated {len(tasks)} tasks.")
        for i, task in enumerate(tasks):
            print(f"\n=== TASK {i+1} ({task['task_type']}) ===")
            print(json.dumps(task, indent=2))
    except Exception as e:
        import traceback

        traceback.print_exc()
