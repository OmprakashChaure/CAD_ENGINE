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
from pipeline.semantic_pipeline import SemanticPipeline


def process_file(dxf_name):
    dxf_path = Path(f"data/raw_dxf/{dxf_name}")
    print(f"\nProcessing: {dxf_name}")

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

    record = SemanticPipeline().run(pipeline_result)
    return record


if __name__ == "__main__":
    try:
        bolt_record = process_file("Hardware_HW01_HexBolt.dxf")
        print("\n--- HEX BOLT FEATURES ---")
        print(json.dumps(bolt_record["features"], indent=2))

        bushing_record = process_file("Fluid_PF02_HexBushing.dxf")
        print("\n--- HEX BUSHING FEATURES ---")
        print(json.dumps(bushing_record["features"], indent=2))
    except Exception as e:
        import traceback

        traceback.print_exc()
