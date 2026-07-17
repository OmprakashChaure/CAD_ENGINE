import json
from collections import defaultdict

# Load current datasets
sem_path = r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\semantic_records.json'
with open(sem_path) as f:
    semantic_records = json.load(f)

jsonl_paths = {
    'train': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\train.jsonl',
    'validation': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\validation.jsonl',
    'test': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\test.jsonl'
}

train_tasks = []
with open(jsonl_paths['train']) as f:
    for line in f:
        train_tasks.append(json.loads(line))

print(f"Loaded {len(semantic_records)} semantic records and {len(train_tasks)} training tasks.")

# ----------------- 1. Complete Semantic Coverage Matrix -----------------
sem_counts = defaultdict(int)
train_target_counts = defaultdict(int)
train_ctx_counts = defaultdict(int)

# Collect semantic facts
for r in semantic_records:
    # overall_dimensions
    for k, v in r.get('overall_dimensions', {}).items():
        if v is not None:
            sem_counts[f"overall_dimensions.{k}"] += 1
            
    # features
    for f in r.get('features', []):
        fc = f.get('feature_class')
        if fc in ['dimension_annotations', 'unknown_facts']:
            continue
        for pk, pv in f.get('parameters', {}).items():
            if pv is not None and pk not in ['positions', 'center', 'text']:
                sem_counts[f"{fc}.{pk}"] += 1
                
    # relationships
    for rel in r.get('relationships', []):
        rtype = rel.get('relationship_type')
        sem_counts[f"relationships.{rtype}"] += 1
        if rtype == 'mirror_symmetry':
            sem_counts["symmetry.mirror_symmetry"] += 1
            
    # hierarchy
    for node in r.get('hierarchy', {}).get('nodes', []):
        sem_counts["hierarchy.node"] += 1
        if node.get('parent_id') is not None:
            sem_counts["containment.parent_child"] += 1
            
    # concentric containment
    for rel in r.get('relationships', []):
        if rel.get('relationship_type') == 'concentric':
            sem_counts["containment.concentric"] += 1

# Map to training tasks
for fkey in sem_counts.keys():
    parts = fkey.split('.')
    group = parts[0]
    sub = parts[1] if len(parts) > 1 else ''
    
    for t in train_tasks:
        target = t['target']
        ctx = t['context']
        
        is_target = False
        is_ctx = False
        
        if group == 'overall_dimensions':
            is_target = False
            is_ctx = 'overall_dimensions' in json.dumps(ctx)
        elif group == 'relationships' or group == 'symmetry':
            is_target = False
            is_ctx = sub in json.dumps(ctx)
        elif group == 'hierarchy' or group == 'containment':
            is_target = False
            is_ctx = sub in json.dumps(ctx) or 'hierarchy' in json.dumps(ctx)
        else:
            if ctx.get('feature_type') == group:
                mapped_props = [sub]
                if group == 'hole_pattern':
                    if sub == 'pcd': mapped_props = ['spacing']
                    elif sub == 'hole_count': mapped_props = ['hole_count']
                    elif sub == 'hole_diameter': mapped_props = ['hole_diameter']
                    elif sub == 'counterbore_diameter': mapped_props = ['hole_diameter']
                    elif sub == 'counterbore_depth': mapped_props = ['profile_dimension']
                elif group == 'hole_group':
                    if sub == 'count': mapped_props = ['hole_count']
                    elif sub == 'diameter': mapped_props = ['bore_diameter', 'hole_diameter']
                    elif sub in ['spacing_x', 'spacing_y']: mapped_props = ['spacing']
                    elif sub == 'counterbore_diameter': mapped_props = ['hole_diameter']
                    elif sub == 'counterbore_depth': mapped_props = ['profile_dimension']
                elif group == 'slot_array':
                    if sub in ['width', 'length']: mapped_props = ['slot_dimension']
                elif group == 'lube_port':
                    if sub == 'diameter': mapped_props = ['hole_diameter']
                elif group == 'thread':
                    if sub == 'nominal_diameter': mapped_props = ['thread_size']
                elif group == 'keyway':
                    if sub in ['width', 'depth']: mapped_props = ['slot_dimension']
                elif group == 'heatsink_fin':
                    if sub == 'count': mapped_props = ['hole_count']
                    elif sub == 'pitch': mapped_props = ['spacing']
                elif group == 'heatsink_core':
                    if sub == 'diameter': mapped_props = ['outer_diameter']
                elif group == 'structural_profile':
                    if sub in ['web_thickness', 'flange_thickness']: mapped_props = ['profile_dimension']
                    elif sub in ['wall_thickness', 'fillet_radius', 'inner_radius', 'outer_radius']:
                        mapped_props = ['wall_thickness', 'profile_dimension']
                elif group == 'bolt':
                    if sub in ['grip_length', 'thread_length', 'across_flats']: mapped_props = ['profile_dimension']
                    elif sub == 'nominal_diameter': mapped_props = ['thread_size']
                elif group == 'screw':
                    if sub in ['length', 'head_diameter', 'drive_size']: mapped_props = ['profile_dimension']
                    elif sub == 'nominal_diameter': mapped_props = ['thread_size']
                elif group == 'hex_head':
                    if sub == 'across_flats': mapped_props = ['profile_dimension']
                elif group == 'hex_drive':
                    if sub == 'size': mapped_props = ['profile_dimension']
                elif group == 'cylindrical_head':
                    if sub in ['head_diameter', 'diameter']: mapped_props = ['outer_diameter']
                elif group == 'fitting':
                    if sub in ['taper_length', 'hex_height', 'neck_length', 'flange_thickness', 'across_flats']: mapped_props = ['profile_dimension']
                elif group == 'pocket':
                    if sub in ['pocket_width', 'pocket_length']: mapped_props = ['pocket_dimension']
                    elif sub == 'perimeter_wall': mapped_props = ['wall_thickness']
                elif group == 'o_ring':
                    if sub == 'o_ring_diameter': mapped_props = ['hole_diameter']
                    elif sub == 'o_ring_groove_depth': mapped_props = ['slot_dimension']
                elif group == 'port':
                    if sub == 'port_diameter': mapped_props = ['hole_diameter']
                    elif sub == 'port_depth': mapped_props = ['slot_dimension']
                    elif sub == 'port_thread': mapped_props = ['thread_size']
                elif group == 'channel':
                    if sub in ['channel_width', 'channel_depth', 'channel_length']: mapped_props = ['slot_dimension']
                elif group == 'shoulder':
                    if sub == 'shoulder_diameter': mapped_props = ['outer_diameter']
                    elif sub == 'shoulder_length': mapped_props = ['profile_dimension']
                elif group == 'cope':
                    if sub == 'cope_radius': mapped_props = ['profile_dimension']
                elif group in ['rib', 'alignment_tab', 'chamfer', 'bend_relief']:
                    if sub == 'value': mapped_props = ['profile_dimension']
                    
                is_target = target['property'] in mapped_props
                is_ctx = sub in ctx.get('feature_parameters_visible', {})
                
        if is_target:
            train_target_counts[fkey] += 1
        if is_ctx:
            train_ctx_counts[fkey] += 1

# ----------------- 2. Empty Context Analysis -----------------
empty_context_tasks = []
for t in train_tasks:
    ctx = t['context']
    has_params = bool(ctx.get('feature_parameters_visible'))
    has_neighbors = bool(ctx.get('neighbor_dimensions')) or bool(ctx.get('topology_neighbors'))
    has_relationships = bool(ctx.get('relationships'))
    
    if not (has_params or has_neighbors or has_relationships):
        empty_context_tasks.append(t)

print(f"Found {len(empty_context_tasks)} empty-context tasks in train split.")

# Prepare results dictionary
results = {
    'matrix': [],
    'empty_count': len(empty_context_tasks),
    'empty_examples': empty_context_tasks[:50]
}

for fkey in sorted(sem_counts.keys()):
    sc = sem_counts[fkey]
    tc_t = train_target_counts[fkey]
    tc_c = train_ctx_counts[fkey]
    
    status = 'LOST'
    if tc_t > 0 and tc_c > 0:
        status = 'TARGET & CONTEXT'
    elif tc_t > 0:
        status = 'TARGET'
    elif tc_c > 0:
        status = 'CONTEXT'
        
    results['matrix'].append({
        'field': fkey,
        'semantic_count': sc,
        'train_count': tc_t + tc_c,
        'status': status
    })

with open('scratch/audit_pre_redesign.json', 'w') as out_f:
    json.dump(results, out_f, indent=2)

print("Dumped pre-redesign audit evidence successfully.")
