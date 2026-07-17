import json

with open('scratch/audit_pre_redesign.json') as f:
    results = json.load(f)

print('Empty context count:', results['empty_count'])
examples = results['empty_examples']

with open('scratch/empty_examples.txt', 'w') as out:
    for idx, t in enumerate(examples):
        out.write(f"### Example {idx+1}:\n")
        out.write(f"* **Drawing ID:** {t['drawing_id']}\n")
        out.write(f"* **Task Type:** {t['task_type']}\n")
        out.write(f"* **Target:** {json.dumps(t['target'])}\n")
        out.write(f"* **Context:** {json.dumps(t['context'])}\n\n")

print("Dumped 50 empty examples to scratch/empty_examples.txt")
