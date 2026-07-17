import json
import re
from pathlib import Path

# Run directories
old_run_dir = Path("data/intermediate/2026_06_25_15_15_42")
new_run_dir = None  # Will detect latest run dir dynamically

def get_latest_run_dir():
    dirs = [d for d in Path("data/intermediate").glob("2026_06_25_*") if d.is_dir()]
    # Exclude the baseline old run dir
    dirs = [d for d in dirs if d.name != "2026_06_25_15_15_42"]
    if not dirs:
        return None
    return sorted(dirs)[-1]

def get_stats(run_dir):
    export_dir = run_dir / "phase7_export"
    splits = ["train.jsonl", "validation.jsonl", "test.jsonl"]
    all_tasks = []
    
    counts = {}
    for split in splits:
        p = export_dir / split
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        all_tasks.append(json.loads(line))
            with open(p, "r", encoding="utf-8") as f:
                counts[split] = sum(1 for line in f if line.strip())
        else:
            counts[split] = 0
            
    total_tasks = len(all_tasks)
    
    families = {}
    for t in all_tasks:
        fam = t.get("task_type")
        families[fam] = families.get(fam, 0) + 1
        
    feature_types = {}
    for t in all_tasks:
        ftype = t.get("context", {}).get("feature_type", "None")
        feature_types[ftype] = feature_types.get(ftype, 0) + 1
        
    context_keys_total = 0
    topology_neighbors_total = 0
    relationships_total = 0
    visible_params_total = 0
    prompt_len_total = 0
    
    for t in all_tasks:
        ctx = t.get("context", {})
        context_keys_total += len(ctx)
        topology_neighbors_total += len(ctx.get("topology_neighbors", []))
        
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
        
    avg_keys = context_keys_total / total_tasks if total_tasks > 0 else 0
    avg_topo = topology_neighbors_total / total_tasks if total_tasks > 0 else 0
    avg_rels = relationships_total / total_tasks if total_tasks > 0 else 0
    avg_params = visible_params_total / total_tasks if total_tasks > 0 else 0
    avg_prompt = prompt_len_total / total_tasks if total_tasks > 0 else 0
    
    # Check log files (we need to locate the log file for this run, but since logs are in different places,
    # let's look in the intermediate run directory for pipeline.log if main.py logs there,
    # or look at the latest system task log)
    rejections = 0
    rejection_reasons = {}
    
    # Try looking for a log file in the run directory first
    log_files = list(run_dir.glob("*.log")) + list(run_dir.glob("**/pipeline*.log"))
    task_logs_dir = Path(r"C:\Users\User\.gemini\antigravity-ide\brain\c3e176c5-6dc9-48f7-954e-b5f4313697d4\.system_generated\tasks")
    if task_logs_dir.exists():
        all_task_logs = list(task_logs_dir.glob("*.log"))
        matching_logs = []
        for pl in all_task_logs:
            try:
                with open(pl, "r", encoding="utf-8", errors="ignore") as f:
                    header = "".join(f.readline() for _ in range(10))
                    if "Found 143 DXF files" in header:
                        matching_logs.append((pl.stat().st_mtime, pl))
            except Exception:
                pass
        if matching_logs:
            matching_logs.sort()
            log_files = [matching_logs[-1][1]]
            
    if log_files:
        latest_log = log_files[-1]
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
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
                            
    return {
        "total_tasks": total_tasks,
        "counts": counts,
        "families": families,
        "feature_types": feature_types,
        "avg_keys": avg_keys,
        "avg_topo": avg_topo,
        "avg_rels": avg_rels,
        "avg_params": avg_params,
        "avg_prompt": avg_prompt,
        "rejections": rejections,
        "rejection_reasons": rejection_reasons
    }

def main():
    new_dir = get_latest_run_dir()
    if not new_dir:
        print("Error: Could not find new run directory under data/intermediate/")
        return
        
    print(f"Comparing Old Exporter ({old_run_dir.name}) vs New Exporter ({new_dir.name})")
    
    old_stats = get_stats(old_run_dir)
    # Since the log parsing of get_stats searches the system tasks logs, for the old run we manually set the baseline log rejections
    # to avoid mixing up log outputs.
    old_stats["rejections"] = 775
    old_stats["rejection_reasons"] = {
        "context could not be matched confidently": 729,
        "insufficient reasoning context": 46
    }
    
    new_stats = get_stats(new_dir)
    
    print("\n" + "="*50)
    print("COMPARISON SUMMARY")
    print("="*50)
    print(f"%-30s %-15s %-15s %-10s" % ("Metric", "Old Exporter", "New Exporter", "Diff"))
    print("-"*75)
    
    diff_tasks = new_stats["total_tasks"] - old_stats["total_tasks"]
    print(f"%-30s %-15d %-15d %-+10d" % ("Total Tasks", old_stats["total_tasks"], new_stats["total_tasks"], diff_tasks))
    print(f"%-30s %-15d %-15d %-+10d" % ("  - Train Split", old_stats["counts"]["train.jsonl"], new_stats["counts"]["train.jsonl"], new_stats["counts"]["train.jsonl"] - old_stats["counts"]["train.jsonl"]))
    print(f"%-30s %-15d %-15d %-+10d" % ("  - Val Split", old_stats["counts"]["validation.jsonl"], new_stats["counts"]["validation.jsonl"], new_stats["counts"]["validation.jsonl"] - old_stats["counts"]["validation.jsonl"]))
    print(f"%-30s %-15d %-15d %-+10d" % ("  - Test Split", old_stats["counts"]["test.jsonl"], new_stats["counts"]["test.jsonl"], new_stats["counts"]["test.jsonl"] - old_stats["counts"]["test.jsonl"]))
    
    diff_rej = new_stats["rejections"] - old_stats["rejections"]
    print(f"%-30s %-15d %-15d %-+10d" % ("Rejected Tasks", old_stats["rejections"], new_stats["rejections"], diff_rej))
    
    print("-"*75)
    print(f"%-30s %-15.2f %-15.2f %-+10.2f" % ("Avg Context Keys", old_stats["avg_keys"], new_stats["avg_keys"], new_stats["avg_keys"] - old_stats["avg_keys"]))
    print(f"%-30s %-15.2f %-15.2f %-+10.2f" % ("Avg Topo Neighbors", old_stats["avg_topo"], new_stats["avg_topo"], new_stats["avg_topo"] - old_stats["avg_topo"]))
    print(f"%-30s %-15.2f %-15.2f %-+10.2f" % ("Avg Relationship Fields", old_stats["avg_rels"], new_stats["avg_rels"], new_stats["avg_rels"] - old_stats["avg_rels"]))
    print(f"%-30s %-15.2f %-15.2f %-+10.2f" % ("Avg Visible Parameters", old_stats["avg_params"], new_stats["avg_params"], new_stats["avg_params"] - old_stats["avg_params"]))
    print(f"%-30s %-15.2f %-15.2f %-+10.2f" % ("Avg Prompt Char Length", old_stats["avg_prompt"], new_stats["avg_prompt"], new_stats["avg_prompt"] - old_stats["avg_prompt"]))
    
    print("\n" + "="*50)
    print("TASK FAMILIES DISTRIBUTION")
    print("="*50)
    all_fams = sorted(list(set(list(old_stats["families"].keys()) + list(new_stats["families"].keys()))))
    for fam in all_fams:
        o_val = old_stats["families"].get(fam, 0)
        n_val = new_stats["families"].get(fam, 0)
        print(f"%-30s %-15d %-15d %-+10d" % (fam, o_val, n_val, n_val - o_val))
        
    print("\n" + "="*50)
    print("REJECTION REASONS BREAKDOWN")
    print("="*50)
    all_reasons = sorted(list(set(list(old_stats["rejection_reasons"].keys()) + list(new_stats["rejection_reasons"].keys()))))
    for reason in all_reasons:
        o_val = old_stats["rejection_reasons"].get(reason, 0)
        n_val = new_stats["rejection_reasons"].get(reason, 0)
        print(f"%-40s %-10d %-10d %-+10d" % (reason[:38], o_val, n_val, n_val - o_val))

if __name__ == "__main__":
    main()
