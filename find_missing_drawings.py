import os
import json

raw_dir = "data/raw_dxf"
run_dir = "data/intermediate/2026_07_17_14_04_10"
semantic_records_path = os.path.join(run_dir, "phase7_export", "semantic_records.json")

# 1. Find all raw DXF basenames
dxf_files = {f[:-4] for f in os.listdir(raw_dir) if f.endswith(".dxf")}

# 2. Find all drawings in semantic records
with open(semantic_records_path) as f:
    records = json.load(f)
record_drawings = {r["drawing_id"] for r in records}

missing = sorted(dxf_files - record_drawings)
print(f"Total raw DXF files: {len(dxf_files)}")
print(f"Total semantic records: {len(record_drawings)}")
print(f"Missing {len(missing)} drawings:")
for m in missing:
    print(f"  - {m}")
