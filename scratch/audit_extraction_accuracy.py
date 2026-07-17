import json
from pathlib import Path

# The 5 drawings we will audit
drawings = [
    "Aero_LW01_MilledPocket",
    "Aero_LW05_IsogridHex",
    "Bearing_Housing_BH01",
    "Electrical_BB01_PhaseBusbar",
    "Gasket_GS01_CylinderHead"
]

run_dir = Path("data/intermediate/2026_06_29_16_40_15/phase1_extraction")

print("==============================================================")
print("AUDITING PHASE 1 EXTRACTION DATA TRUTH (5 RANDOM DRAWINGS)")
print("==============================================================\n")

for name in drawings:
    json_path = run_dir / f"{name}.json"
    if not json_path.exists():
        print(f"File {json_path} does not exist. Skipping.")
        continue
        
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
        
    entities = data.get("entities", [])
    
    # Calculate geometric statistics
    geom_types = {}
    dimension_texts = []
    layers = set()
    
    for ent in entities:
        etype = ent.get("entity_type")
        layer = ent.get("layer")
        layers.add(layer)
        geom_types[etype] = geom_types.get(etype, 0) + 1
        
        # If it is a dimension or text annotation
        if etype == "DIMENSION":
            geom = ent.get("geometry", {})
            val = geom.get("value")
            text = geom.get("text")
            dimension_texts.append(f"DIM: {text} (Value: {val})")
        elif etype in ("TEXT", "MTEXT"):
            geom = ent.get("geometry", {})
            text = geom.get("text")
            val = geom.get("numeric_value")
            dimension_texts.append(f"TEXT: '{text}' (Val: {val})")

    print(f"> Drawing Name: {name}.dxf / {name}.pdf")
    print(f"  Total Extracted Entities: {len(entities)}")
    print(f"  Entity Type Count: {geom_types}")
    print(f"  Layers Found: {sorted(list(layers))}")
    print(f"  Dimension Callouts Extracted:")
    for dt in dimension_texts:
        print(f"    - {dt}")
    print("-" * 62)
