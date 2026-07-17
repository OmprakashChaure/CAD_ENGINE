import json
import os
import re

reasoning_dir = "data/intermediate/2026_07_17_14_04_10/phase8_reasoning"
splits = ["train.jsonl", "validation.jsonl", "test.jsonl"]

total_v2 = 0
total_reasoning = 0
failures = []

for split in splits:
    path = os.path.join(reasoning_dir, split)
    if not os.path.exists(path):
        continue
        
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            task = json.loads(line)
            task_class = task.get("task_class", "v2")
            
            if task_class == "v2":
                total_v2 += 1
                continue
                
            total_reasoning += 1
            
            # 1. Schema Validation
            required_keys = {"drawing_id", "task_class", "context", "target", "system", "user", "assistant", "reasoning_metadata"}
            missing_keys = required_keys - set(task.keys())
            if missing_keys:
                failures.append(f"{split}:{line_num} Missing keys: {missing_keys}")
                
            # 2. Leakage Validation
            target_val = task.get("target", {}).get("value")
            user_text = task.get("user", "")
            val_str = str(target_val)
            if re.search(rf'\b{re.escape(val_str)}\b', user_text):
                failures.append(f"{split}:{line_num} Leakage found for value {target_val}")
                
            # 3. Mathematical Validation
            meta = task.get("reasoning_metadata", {})
            calc = meta.get("calculation", "")
            # Verify calculation output matches assistant response
            if calc:
                parts = calc.split("=")
                if len(parts) == 2:
                    ans = parts[1].strip()
                    if abs(float(ans) - float(target_val)) > 0.001:
                        failures.append(f"{split}:{line_num} Math calculation mismatch: {calc} vs {target_val}")

print(f"Verified Stage 3 Dataset output splits:")
print(f"  V2 tasks: {total_v2}")
print(f"  Reasoning tasks: {total_reasoning}")
print(f"  Failures/Alerts: {len(failures)}")
for f in failures[:10]:
    print(f"    - {f}")
