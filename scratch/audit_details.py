import json
import random
from collections import defaultdict

# Set random seed for deterministic "random" selection
random.seed(42)

sem_path = r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\semantic_records.json'
with open(sem_path) as f:
    semantic_records = json.load(f)

jsonl_paths = {
    'train': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\train.jsonl',
    'validation': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\validation.jsonl',
    'test': r'C:\Users\User\Downloads\CAD_ENGINE\CAD_ENGINE\data\intermediate\2026_06_23_18_38_17\phase7_export\test.jsonl'
}

splits = {}
for split, path in jsonl_paths.items():
    with open(path) as f:
        splits[split] = [json.loads(line) for line in f]

# ----------------- STEP 1 & 4: inventory of fields -----------------
# Let's write down a clear classification for every field in semantic_records.json.
# We'll count occurrences and track a sample drawing and value.
inventory = defaultdict(lambda: {'count': 0, 'drawings': set(), 'examples': []})

note_keywords = ['note', 'matl', 'material', 'break all sharp edges', 'edges', 'tolerance', 'finish', 'spec']
mfg_keywords = ['6061-t6', 'aluminum', 'steel', 'brass', 'thk', 'bushing', 'press-fit', 'tolerance', '%%p', 'weld', 'thread_designation', 'bore_type']

for r in semantic_records:
    dwg_id = r.get('drawing_id')
    
    # overall_dimensions
    ov = r.get('overall_dimensions', {})
    for k, v in ov.items():
        if v is not None:
            fkey = f"overall_dimensions.{k}"
            inventory[fkey]['count'] += 1
            inventory[fkey]['drawings'].add(dwg_id)
            inventory[fkey]['examples'].append(v)
            
    # features
    for f in r.get('features', []):
        fc = f.get('feature_class')
        params = f.get('parameters', {})
        
        if fc == 'dimension_annotations':
            for dim in params.get('dimensions', []) + params.get('pattern_dimensions', []):
                text = dim.get('text')
                val = dim.get('value')
                text_lower = (text or '').lower()
                
                fkey = "dimension_annotations.text"
                inventory[fkey]['count'] += 1
                inventory[fkey]['drawings'].add(dwg_id)
                inventory[fkey]['examples'].append(text)
                
                if any(kw in text_lower for kw in ['note', 'break all sharp', 'finish', 'edges']):
                    fkey_note = "engineering_notes.text"
                    inventory[fkey_note]['count'] += 1
                    inventory[fkey_note]['drawings'].add(dwg_id)
                    inventory[fkey_note]['examples'].append(text)
                if any(kw in text_lower for kw in mfg_keywords) or '%%p' in text_lower or 'matl' in text_lower:
                    fkey_mfg = "manufacturing_knowledge.text"
                    inventory[fkey_mfg]['count'] += 1
                    inventory[fkey_mfg]['drawings'].add(dwg_id)
                    inventory[fkey_mfg]['examples'].append(text)
            continue
            
        if fc == 'unknown_facts':
            for dim in params.get('unknown_dimensions', []) + params.get('unknown_annotations', []):
                text = dim.get('text')
                text_lower = (text or '').lower()
                if any(kw in text_lower for kw in ['note', 'break all sharp', 'finish', 'edges']):
                    fkey_note = "engineering_notes.text"
                    inventory[fkey_note]['count'] += 1
                    inventory[fkey_note]['drawings'].add(dwg_id)
                    inventory[fkey_note]['examples'].append(text)
                if any(kw in text_lower for kw in mfg_keywords) or '%%p' in text_lower or 'matl' in text_lower:
                    fkey_mfg = "manufacturing_knowledge.text"
                    inventory[fkey_mfg]['count'] += 1
                    inventory[fkey_mfg]['drawings'].add(dwg_id)
                    inventory[fkey_mfg]['examples'].append(text)
            continue
            
        for pk, pv in params.items():
            if pv is None or pk in ['positions', 'center', 'text']:
                if pk == 'bore_type' and pv:
                    fkey_mfg = "manufacturing_knowledge.bore_type"
                    inventory[fkey_mfg]['count'] += 1
                    inventory[fkey_mfg]['drawings'].add(dwg_id)
                    inventory[fkey_mfg]['examples'].append(pv)
                continue
                
            if pk in ['thread_designation', 'pitch'] and pv:
                fkey_mfg = f"manufacturing_knowledge.{pk}"
                inventory[fkey_mfg]['count'] += 1
                inventory[fkey_mfg]['drawings'].add(dwg_id)
                inventory[fkey_mfg]['examples'].append(pv)
                
            fkey = f"{fc}.{pk}"
            inventory[fkey]['count'] += 1
            inventory[fkey]['drawings'].add(dwg_id)
            inventory[fkey]['examples'].append(pv)

    # relationships
    rels = r.get('relationships', [])
    for rel in rels:
        rtype = rel.get('relationship_type')
        fkey = f"relationships.{rtype}"
        inventory[fkey]['count'] += 1
        inventory[fkey]['drawings'].add(dwg_id)
        inventory[fkey]['examples'].append(rel.get('feature_ids'))
        
        if rtype == 'mirror_symmetry':
            fkey_sym = "symmetry.mirror_symmetry"
            inventory[fkey_sym]['count'] += 1
            inventory[fkey_sym]['drawings'].add(dwg_id)
            inventory[fkey_sym]['examples'].append(rel.get('parameters'))

    # hierarchy
    hier = r.get('hierarchy', {})
    nodes = hier.get('nodes', [])
    for node in nodes:
        fkey = "hierarchy.node"
        inventory[fkey]['count'] += 1
        inventory[fkey]['drawings'].add(dwg_id)
        inventory[fkey]['examples'].append(node.get('candidate_id'))
        
        if node.get('parent_id') is not None:
            fkey_cnt = "containment.parent_child"
            inventory[fkey_cnt]['count'] += 1
            inventory[fkey_cnt]['drawings'].add(dwg_id)
            inventory[fkey_cnt]['examples'].append((node.get('parent_id'), node.get('candidate_id')))
            
    # concentric relationships are also containment
    for rel in rels:
        if rel.get('relationship_type') == 'concentric':
            fkey_cnt = "containment.concentric"
            inventory[fkey_cnt]['count'] += 1
            inventory[fkey_cnt]['drawings'].add(dwg_id)
            inventory[fkey_cnt]['examples'].append(rel.get('feature_ids'))

# Save master inventory
master_table = []
for key, data in sorted(inventory.items()):
    dwgs = list(data['drawings'])
    ex_dwg = dwgs[0] if dwgs else 'N/A'
    ex_val = data['examples'][0] if data['examples'] else 'N/A'
    master_table.append({
        'field': key,
        'count': data['count'],
        'example_drawing': ex_dwg,
        'example_value': str(ex_val)
    })

print(f"Discovered {len(master_table)} fields in semantic inventory.")

# Dump sample verification candidates
def get_sample_detail(t):
    dwg_id = t.get('drawing_id')
    # Find matching semantic record
    sem_rec = next((r for r in semantic_records if r['drawing_id'] == dwg_id), None)
    return {
        'drawing_id': dwg_id,
        'task_type': t.get('task_type'),
        'context': t.get('context'),
        'target': t.get('target'),
        'semantic_record': sem_rec
    }

samples = {
    'train': [get_sample_detail(t) for t in random.sample(splits['train'], 20)],
    'validation': [get_sample_detail(t) for t in random.sample(splits['validation'], 10)],
    'test': [get_sample_detail(t) for t in random.sample(splits['test'], 10)]
}

# Write results
with open('scratch/audit_details.json', 'w') as out_f:
    json.dump({
        'master_table': master_table,
        'samples': samples
    }, out_f, indent=2)

print("Inventory and samples exported successfully.")
