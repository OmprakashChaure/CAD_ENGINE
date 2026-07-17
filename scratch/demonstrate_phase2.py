import sys
import json
from pathlib import Path

# Add root folder to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from pipeline.extraction_pipeline import ExtractionPipeline
from pipeline.topology_pipeline import TopologyPipeline

def main():
    dxf_sample = Path("data/raw_dxf/Aero_LW01_MilledPocket.dxf")
    if not dxf_sample.exists():
        print(f"Error: Sample file {dxf_sample} not found!")
        return

    print("======================================================================")
    print(f"DEMONSTRATING PHASE 2 (Topology Graph Construction) on: {dxf_sample.name}")
    print("======================================================================\n")

    # Run Phase 1 to extract and filter geometry
    print("Executing Phase 1 Extraction...")
    phase1_result = ExtractionPipeline(str(dxf_sample)).run()
    entities = phase1_result["entities"]
    print(f"Phase 1 complete. Extracted {len(entities)} geometry entities.")

    # Run Phase 2
    print("\nExecuting Phase 2 Topology Pipeline...")
    topology = TopologyPipeline()
    result = topology.run(entities)

    shared_vertices = result["shared_vertices"]
    adjacency_list = result["adjacency_list"]
    orphans = result["orphan_entities"]
    stats = result["statistics"]

    print("\n--- TOPOLOGY STATISTICS ---")
    print(f"Total Input Entities: {stats.get('total_input_entities')}")
    print(f"Total Shared Vertices (Snapped Points): {stats.get('shared_vertices')}")
    print(f"Total Edge Connections: {stats.get('total_edges')}")
    print(f"Orphan Entities: {stats.get('orphan_entities')}")

    print("\n--- SAMPLE VERTEX MAP (Shared Coordinates -> Entity IDs) ---")
    # Show first 5 vertices that link multiple lines
    count = 0
    for coord_str, linked_ids in shared_vertices.items():
        if len(linked_ids) >= 2:
            print(f"Vertex {coord_str} connects: {linked_ids}")
            count += 1
            if count >= 5:
                break

    print("\n--- SAMPLE ADJACENCY LIST (Line IDs -> Touched Line IDs) ---")
    # Show the adjacency of some entities
    count = 0
    for ent_id, connected_ids in list(adjacency_list.items())[:5]:
        print(f"Entity '{ent_id}' connects directly to: {connected_ids}")
        count += 1

    if orphans:
        print("\n--- ORPHAN ENTITIES DETECTED ---")
        print(orphans)

if __name__ == "__main__":
    main()
