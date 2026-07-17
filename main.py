from pathlib import Path
import json
from datetime import datetime

from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.topology_pipeline import TopologyPipeline
from pipeline.structural_pipeline import StructuralPipeline
from pipeline.feature_pipeline import FeaturePipeline
from pipeline.refinement_pipeline import RefinementPipeline
from pipeline.context_pipeline import ContextPipeline
from pipeline.dataset_pipeline import DatasetPipeline
from pipeline.dataset_pipeline import DatasetExporter
from utils.logger import get_logger


logger = get_logger(__name__)


INPUT_DIR = Path("data/raw_dxf")

run_id = datetime.now().strftime(
    "%Y_%m_%d_%H_%M_%S"
)

run_dir = Path(
    f"data/intermediate/{run_id}"
)

run_dir.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_DIR = (
    run_dir / "phase1_extraction"
)

TOPOLOGY_DIR = (
    run_dir / "phase2_topology"
)

STRUCTURAL_DIR = (
    run_dir / "phase3_structural"
)

FEATURES_DIR = (
    run_dir / "phase4_features"
)

REFINEMENT_DIR = (
    run_dir / "phase5_refinement"
)

CONTEXT_DIR = (
    run_dir / "phase6_context"
)

DATASET_DIR = (
    run_dir / "phase7_dataset"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TOPOLOGY_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURAL_DIR.mkdir(parents=True, exist_ok=True)
FEATURES_DIR.mkdir(parents=True, exist_ok=True)
REFINEMENT_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
DATASET_DIR.mkdir(parents=True, exist_ok=True)


def main():

    dxf_files = list(INPUT_DIR.glob("*.dxf"))

    logger.info(f"Found {len(dxf_files)} DXF files")

    all_dataset_results = []

    for dxf_file in dxf_files:

        logger.info(f"Processing: {dxf_file.name}")

        try:
            # Phase 1: Extraction + Filtering
            pipeline = ExtractionPipeline(str(dxf_file))
            extraction_result = pipeline.run()
        except Exception as exc:
            logger.error(f"SKIPPING {dxf_file.name}: {exc}")
            continue

        output_path = (
            OUTPUT_DIR / f"{dxf_file.stem}.json"
        )

        with open(output_path, "w") as fp:
            json.dump(
                extraction_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved filtered entities: {output_path}"
        )

        # Phase 2: Topology Graph Construction
        kept_entities = extraction_result["entities"]

        topology = TopologyPipeline()
        topology_result = topology.run(kept_entities)

        topology_path = (
            TOPOLOGY_DIR / f"{dxf_file.stem}_topology.json"
        )

        with open(topology_path, "w") as fp:
            json.dump(
                topology_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved topology graph: {topology_path}"
        )

        # Phase 3: Structural Engineering Recognition
        structural = StructuralPipeline()
        structural_result = structural.run(
            kept_entities, topology_result
        )

        structural_path = (
            STRUCTURAL_DIR / f"{dxf_file.stem}_structural.json"
        )

        with open(structural_path, "w") as fp:
            json.dump(
                structural_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved structural analysis: {structural_path}"
        )

        # Phase 4: Feature Candidate Detection
        feature_pipeline = FeaturePipeline()
        feature_result = feature_pipeline.run(
            kept_entities, structural_result
        )

        features_path = (
            FEATURES_DIR / f"{dxf_file.stem}_features.json"
        )

        with open(features_path, "w") as fp:
            json.dump(
                feature_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved feature candidates: {features_path}"
        )

        # Phase 5: Feature Candidate Refinement
        refinement = RefinementPipeline()
        refinement_result = refinement.run(feature_result)

        refinement_path = (
            REFINEMENT_DIR / f"{dxf_file.stem}_refinement.json"
        )

        with open(refinement_path, "w") as fp:
            json.dump(
                refinement_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved refinement analysis: {refinement_path}"
        )

        # Phase 6: Engineering Context Organization
        context = ContextPipeline()
        context_result = context.run(feature_result, refinement_result)

        context_path = (
            CONTEXT_DIR / f"{dxf_file.stem}_context.json"
        )

        with open(context_path, "w") as fp:
            json.dump(
                context_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved context analysis: {context_path}"
        )

        # Log context statistics
        context_stats = context_result.get("statistics", {})
        rel_stats = context_stats.get("relationships", {})
        cluster_stats = context_stats.get("clusters", {})
        logger.info(
            f"Context: relationships={rel_stats.get('total_relationships', 0)} "
            f"clusters={cluster_stats.get('total_clusters', 0)} "
            f"connected_candidates={rel_stats.get('connected_candidates', 0)}"
        )

        # Phase 7: Supervised Dataset Generation
        dataset = DatasetPipeline()
        dataset_result = dataset.run(
            kept_entities,
            topology_result,
            structural_result,
            feature_result,
            refinement_result,
            drawing_id=dxf_file.stem,
            context_result=context_result,
        )

        dataset_path = (
            DATASET_DIR / f"{dxf_file.stem}_dataset.json"
        )

        with open(dataset_path, "w") as fp:
            json.dump(
                dataset_result,
                fp,
                indent=2,
                default=str,
            )

        logger.info(
            f"Saved dataset: {dataset_path}"
        )

        all_dataset_results.append({
            "drawing_id": dxf_file.stem,
            "entities": kept_entities,
            "feature_result": feature_result,
            "structural_result": structural_result,
            "refinement_result": refinement_result,
            "topology_result": topology_result,
            "context_result": context_result,
            "dataset_result": dataset_result,
        })

    # Final Export: semantic engineering inference tasks
    if all_dataset_results:
        export_dir = run_dir / "phase7_export"
        exporter = DatasetExporter(export_dir)
        metadata = exporter.export(all_dataset_results)

        logger.info(
            f"EXPORT COMPLETE: "
            f"train={metadata['splits']['train']['count']} "
            f"val={metadata['splits']['validation']['count']} "
            f"test={metadata['splits']['test']['count']}"
        )
        
        # Phase 8: Stage 3 Reasoning Pipeline Execution
        try:
            from pipeline.reasoning_pipeline import ReasoningPipeline
            reasoning_pipeline = ReasoningPipeline(str(run_dir))
            reasoning_result = reasoning_pipeline.run()
            logger.info("Stage 3 Reasoning Pipeline completed successfully.")
        except Exception as exc:
            logger.error(f"Reasoning Pipeline failed: {exc}")


if __name__ == "__main__":
    main()