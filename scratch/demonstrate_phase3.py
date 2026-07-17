import sys
import json
from pathlib import Path

# Add root folder to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.topology_pipeline import TopologyPipeline
from pipeline.structural_pipeline import StructuralPipeline

def main():
    # We will run this on Bearing_Housing_BH01 because it contains concentric circles AND loop profiles!
    dxf_sample = Path("data/raw_dxf/Bearing_Housing_BH01.dxf")
    if not dxf_sample.exists():
        print(f"Error: Sample file {dxf_sample} not found!")
        return

    print("======================================================================")
    print(f"DEMONSTRATING PHASE 3 (Structural Recognition) on: {dxf_sample.name}")
    print("======================================================================\n")

    # Run Phase 1
    print("Running Phase 1 Extraction...")
    phase1_result = ExtractionPipeline(str(dxf_sample)).run()
    entities = phase1_result["entities"]

    # Run Phase 2
    print("Running Phase 2 Topology...")
    topology_result = TopologyPipeline().run(entities)

    # Run Phase 3
    print("Running Phase 3 Structural Recognition...")
    structural = StructuralPipeline()
    result = structural.run(entities, topology_result)

    contours = result["contours"]
    loops = result["loops"]
    concentric = result["concentric_groups"]
    regions = result["regions"]
    hierarchy = result["contour_hierarchy"]
    stats = result["statistics"]

    print("\n--- PHASE 3 STATISTICS ---")
    print(f"Total Traced Contours: {stats['contours']['total_contours']}")
    print(f"Total Closed Loops: {stats['loops']['total_loops']}")
    print(f"Total Concentric Circle Groups: {stats['concentric']['total_groups']}")
    print(f"Total Region Islands: {stats['regions']['total_regions']}")
    print(f"Outer Contours (Depth 0): {stats['hierarchy']['outer']}")
    print(f"Inner Contours (Depth 1+): {stats['hierarchy']['inner']}")

    print("\n--- DETECTED CLOSED LOOPS (Geometry Cycles) ---")
    for i, loop in enumerate(loops.get("loops", [])):
        print(f"Loop {i+1}: {loop}")

    print("\n--- CONCENTRIC GROUPS (Bores & Concentric Rings) ---")
    for cg in concentric.get("concentric_groups", []):
        print(f"Group {cg.get('group_id')}:")
        print(f"  Center: {cg.get('center')}")
        print(f"  Radii: {cg.get('radii')}")
        print(f"  Entities: {cg.get('entity_ids')}")

    print("\n--- CONTOUR HIERARCHY (Nesting Containment) ---")
    for h_item in hierarchy.get("hierarchy", []):
        print(f"Entity '{h_item.get('entity_id')}' -> Role: {h_item.get('contour_role')}, Nesting Depth: {h_item.get('nesting_depth')}")

if __name__ == "__main__":
    main()
