import sys
from pathlib import Path

# Add root folder to sys.path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from pipeline.extraction_pipeline import ExtractionPipeline

def main():
    # We will use one of our actual raw DXF drawings as a sample
    dxf_sample = Path("data/raw_dxf/Aero_LW01_MilledPocket.dxf")
    if not dxf_sample.exists():
        print(f"Error: Sample file {dxf_sample} not found!")
        return

    print("======================================================================")
    print(f"DEMONSTRATING PHASE 1 (Extraction & Filtering) on: {dxf_sample.name}")
    print("======================================================================\n")

    # Initialize Phase 1 Pipeline
    pipeline = ExtractionPipeline(str(dxf_sample))
    
    # Run the pipeline
    result = pipeline.run()

    # Retrieve components
    entities = result["entities"]
    quarantined = result["quarantined_entities"]
    removed = result["removed_entities"]
    reports = result["filter_reports"]

    print("\n--- FILTERING STAGE REPORTS ---")
    for r in reports:
        print(f"Filter: {r['filter']}")
        print(f"  Kept: {r['statistics'].get('kept_entities', 0)}")
        print(f"  Quarantined: {r['statistics'].get('quarantined_entities', 0)}")
        print(f"  Removed: {r['statistics'].get('removed_entities', 0)}")

    print("\n--- STAGE SUMMARY ---")
    print(f"Final Kept Geometry Entities: {len(entities)}")
    print(f"Quarantined Entities (stored for annotations): {len(quarantined)}")
    print(f"Permanently Removed Entities (degenerate/noise): {len(removed)}")

    if entities:
        print("\n--- SAMPLE KEPT GEOMETRY ENTITY ---")
        sample_geom = entities[0]
        import json
        print(json.dumps(sample_geom, indent=2))

    if quarantined:
        print("\n--- SAMPLE QUARANTINED ANNOTATION/TEXT ENTITY ---")
        sample_quar = quarantined[0]
        import json
        print(json.dumps(sample_quar, indent=2))

if __name__ == "__main__":
    main()
