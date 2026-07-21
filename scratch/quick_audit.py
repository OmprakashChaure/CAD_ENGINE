import os
import ast
from pathlib import Path
from collections import defaultdict

# Exclude directories that are not part of the source code or are third-party/cache
EXCLUDE_DIRS = {".git", ".pytest_cache", "__pycache__", "Cad_Engine", "data", "outputs", "pdf", "archive"}

def get_all_py_files(root_dir):
    py_files = []
    for r, d, fs in os.walk(root_dir):
        # Filter directories in-place
        d[:] = [dirname for dirname in d if dirname not in EXCLUDE_DIRS and not dirname.startswith(".")]
        for f in fs:
            if f.endswith(".py"):
                py_files.append(Path(os.path.join(r, f)).resolve())
    return py_files

def parse_imports(file_path):
    imports = set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.add(name.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
    except Exception as e:
        # Fallback to simple regex if ast fails
        import re
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r'^\s*(?:import\s+([\w\.,\s]+)|from\s+([\w\.]+)\s+import)', content, re.MULTILINE):
                imp = match.group(1) or match.group(2)
                if imp:
                    parts = [x.strip() for x in re.split(r'[\s,]+', imp)]
                    for part in parts:
                        if part:
                            imports.add(part)
        except Exception:
            pass
    return imports

def main():
    root = Path(".").resolve()
    all_py = get_all_py_files(root)
    
    # Map from relative module name to absolute file path
    # e.g. "pipeline.dataset_pipeline" -> Path(...)
    module_to_file = {}
    file_to_module = {}
    
    for p in all_py:
        rel = p.relative_to(root)
        parts = rel.parts
        file_to_module[p] = ".".join(parts[:-1]) + "." + parts[-1].replace(".py", "") if len(parts) > 1 else parts[-1].replace(".py", "")
        
        # Register module name
        if parts[0] in {"core", "pipeline", "utils", "schemas", "tools"}:
            mod_name = ".".join(parts[:-1]) + "." + parts[-1].replace(".py", "")
            module_to_file[mod_name] = p
            if parts[-1] == "__init__.py":
                module_to_file[".".join(parts[:-1])] = p
        elif len(parts) == 1:
            module_to_file[parts[0].replace(".py", "")] = p
            
    # Trace imports
    imported_by = defaultdict(list)
    # Sort modules by length descending to match most specific modules first (e.g. 'core.reader.dxf_loader' before 'core')
    sorted_modules = sorted(module_to_file.items(), key=lambda x: len(x[0]), reverse=True)
    for p in all_py:
        rel = p.relative_to(root)
        imports = parse_imports(p)
        for imp in imports:
            # Find if this import matches any local module
            for mod_name, mod_file in sorted_modules:
                if imp == mod_name or imp.startswith(mod_name + "."):
                    imported_by[mod_file].append(p)
                    break
                    
    # Categorize files
    production_files = []
    test_files = []
    scratch_files = []
    root_scripts = []
    
    for p in all_py:
        rel = p.relative_to(root)
        parts = rel.parts
        if "tests" in parts:
            test_files.append(p)
        elif "scratch" in parts:
            scratch_files.append(p)
        elif len(parts) == 1:
            root_scripts.append(p)
        else:
            production_files.append(p)
            
    # Trace reachable from main.py
    main_path = root / "main.py"
    reachable = set()
    
    def dfs(file_path):
        if file_path in reachable:
            return
        reachable.add(file_path)
        # Find what this file imports
        imports = parse_imports(file_path)
        for imp in imports:
            for mod_name, mod_file in sorted_modules:
                if imp == mod_name or imp.startswith(mod_name + "."):
                    dfs(mod_file)
                    break
                    
    if main_path.exists():
        dfs(main_path)
        
    print("=== WORKSPACE PYTHON FILES AUDIT ===")
    print(f"Total Python Files found: {len(all_py)}")
    print(f"Production Files: {len(production_files)}")
    print(f"Test Files: {len(test_files)}")
    print(f"Scratch Files: {len(scratch_files)}")
    print(f"Root Scripts: {len(root_scripts)}")
    
    print("\n--- ACTIVE PRODUCTION FILES (Reachable from main.py) ---")
    active = sorted([p.relative_to(root) for p in production_files if p in reachable or p == main_path])
    for act in active:
        print(f"- {act}")
        
    print("\n--- UNUSED PRODUCTION FILES (NOT Reachable from main.py) ---")
    unused = sorted([p.relative_to(root) for p in production_files if p not in reachable and p != main_path])
    for un in unused:
        importers = [str(imp.relative_to(root)) for imp in imported_by[root / un]]
        importers_str = f" (Imported by: {', '.join(importers)})" if importers else " (Warning: COMPLETELY UNIMPORTED!)"
        print(f"- {un}{importers_str}")
        
    print("\n--- ROOT SCRIPTS (Useful or Standalone/Diagnostic) ---")
    for rs in sorted([p.relative_to(root) for p in root_scripts]):
        importers = [str(imp.relative_to(root)) for imp in imported_by[root / rs]]
        importers_str = f" (Imported by: {', '.join(importers)})" if importers else " (Standalone)"
        print(f"- {rs}{importers_str}")
        
    print("\n--- TEST FILES ---")
    for tf in sorted([p.relative_to(root) for p in test_files]):
        print(f"- {tf}")

if __name__ == "__main__":
    main()
