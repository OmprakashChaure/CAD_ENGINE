import json
import re
from pathlib import Path

run_dir = Path("data/intermediate/2026_06_25_15_15_42")
export_dir = run_dir / "phase7_export"
log_file = Path(r"C:\Users\User\.gemini\antigravity-ide\brain\c3e176c5-6dc9-48f7-954e-b5f4313697d4\.system_generated\tasks\task-5848.log")

def main():
    splits = ["train.jsonl", "validation.jsonl", "test.jsonl"]
    all_tasks = []
    for split in splits:
        p = export_dir / split
        if p.exists():
            with open(p, "r") as f:
                for line in f:
                    if line.strip():
                        all_tasks.append(json.loads(line))
                        
    total_tasks = len(all_tasks)
    print(f"Total generated samples: {total_tasks}")
    
    # Let's count tasks in each file
    counts = {}
    for split in splits:
        p = export_dir / split
        if p.exists():
            with open(p, "r") as f:
                counts[split] = sum(1 for line in f if line.strip())
        else:
            counts[split] = 0
            
    print(f"Train count: {counts['train.jsonl']}")
    print(f"Validation count: {counts['validation.jsonl']}")
    print(f"Test count: {counts['test.jsonl']}")
    
    # Task family distribution
    families = {}
    for t in all_tasks:
        fam = t.get("task_type")
        families[fam] = families.get(fam, 0) + 1
    print("\nTask family distribution:")
    for fam, count in sorted(families.items()):
        print(f"  - {fam}: {count}")
        
    # Feature type distribution
    feature_types = {}
    for t in all_tasks:
        ftype = t.get("context", {}).get("feature_type", "None")
        feature_types[ftype] = feature_types.get(ftype, 0) + 1
    print("\nFeature type distribution:")
    for ftype, count in sorted(feature_types.items()):
        print(f"  - {ftype}: {count}")
        
    # Average context sizes and other fields
    context_keys_total = 0
    topology_neighbors_total = 0
    relationships_total = 0
    visible_params_total = 0
    prompt_len_total = 0
    
    for t in all_tasks:
        ctx = t.get("context", {})
        context_keys_total += len(ctx)
        topology_neighbors_total += len(ctx.get("topology_neighbors", []))
        
        # relationships include relationships, symmetries, concentric_features, nesting_context
        rels = len(ctx.get("relationships", []))
        if "symmetries" in ctx:
            rels += len(ctx["symmetries"])
        if "concentric_features" in ctx:
            rels += len(ctx["concentric_features"])
        if ctx.get("nesting_context"):
            rels += 1
        relationships_total += rels
        
        visible_params_total += len(ctx.get("feature_parameters_visible", {}))
        prompt_len_total += len(json.dumps(ctx))
        
    if total_tasks > 0:
        print(f"\nMetrics (Averages):")
        print(f"  - Average context keys: {context_keys_total / total_tasks:.2f}")
        print(f"  - Average topology neighbors: {topology_neighbors_total / total_tasks:.2f}")
        print(f"  - Average relationship features: {relationships_total / total_tasks:.2f}")
        print(f"  - Average visible parameters: {visible_params_total / total_tasks:.2f}")
        print(f"  - Average prompt/context char length: {prompt_len_total / total_tasks:.2f}")
        
    # Parse log file for rejections
    rejections = 0
    rejection_reasons = {}
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "Rejected task" in line:
                    rejections += 1
                    reason_match = re.search(r"because (.+)\.$|due to (.+)\.$", line)
                    if reason_match:
                        reason = reason_match.group(1) or reason_match.group(2)
                        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    else:
                        reason_match_alt = re.search(r"Rejected task \w+ for drawing \w+ (.+)", line)
                        if reason_match_alt:
                            rejection_reasons[reason_match_alt.group(1)] = rejection_reasons.get(reason_match_alt.group(1), 0) + 1
                        else:
                            rejection_reasons["unknown reason"] = rejection_reasons.get("unknown reason", 0) + 1
                        
    print(f"\nNumber of rejected samples: {rejections}")
    print("Rejection reasons:")
    for reason, count in rejection_reasons.items():
        print(f"  - {reason}: {count}")

if __name__ == "__main__":
    main()
