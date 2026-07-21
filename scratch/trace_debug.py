import scratch.quick_audit
import pathlib

root = pathlib.Path('.').resolve()
all_py = scratch.quick_audit.get_all_py_files(root)

# Build module_to_file
module_to_file = {}
for p in all_py:
    rel = p.relative_to(root)
    parts = rel.parts
    if parts[0] in {"core", "pipeline", "utils", "schemas", "tools"}:
        mod_name = ".".join(parts[:-1]) + "." + parts[-1].replace(".py", "")
        module_to_file[mod_name] = p
        if parts[-1] == "__init__.py":
            module_to_file[".".join(parts[:-1])] = p
    elif len(parts) == 1:
        module_to_file[parts[0].replace(".py", "")] = p

# Parse main.py
main_path = root / "main.py"
main_imports = scratch.quick_audit.parse_imports(main_path)
print("main.py imports:", main_imports)

extraction_pipeline_path = module_to_file.get("pipeline.extraction_pipeline")
print("pipeline.extraction_pipeline path:", extraction_pipeline_path)

ext_imports = scratch.quick_audit.parse_imports(extraction_pipeline_path)
print("pipeline.extraction_pipeline imports:", ext_imports)

for imp in ext_imports:
    matched = False
    for mod_name, mod_file in module_to_file.items():
        if imp == mod_name or imp.startswith(mod_name + "."):
            print(f"  imp '{imp}' matches module '{mod_name}' -> file '{mod_file.relative_to(root)}'")
            matched = True
            break
    if not matched:
        print(f"  imp '{imp}' does NOT match any local module")
