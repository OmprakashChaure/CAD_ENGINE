import os
import re
from pathlib import Path
from collections import defaultdict

# Define directories to exclude from core/pipeline imports check
EXCLUDE_DIRS = {"Cad_Engine", ".git", "__pycache__", ".pytest_cache"}

def get_all_py_files(root_dir):
    py_files = []
    for r, d, fs in os.walk(root_dir):
        # Skip excluded dirs
        d[:] = [dirname for dirname in d if dirname not in EXCLUDE_DIRS]
        for f in fs:
            if f.endswith(".py"):
                py_files.append(Path(os.path.join(r, f)).resolve())
    return py_files

def main():
    root = Path(".").resolve()
    all_py = get_all_py_files(root)
    
    # Map from absolute path to relative path for output
    rel_paths = {p: p.relative_to(root) for p in all_py}
    
    # Store imports for each file
    # We will search for standard python import statements:
    # "import xxx" or "from xxx import yyy"
    file_imports = defaultdict(set)
    
    # Module name mapping to file path
    # e.g., 'core.classifiers.geometry_normalizer' -> .../core/classifiers/geometry_normalizer.py
    module_to_file = {}
    for p in all_py:
        # Determine module name based on relative path from root
        rel = rel_paths[p]
        parts = rel.parts
        if parts[0] in {"core", "pipeline", "utils", "schemas", "tools"}:
            mod_name = ".".join(parts[:-1]) + "." + parts[-1].replace(".py", "")
            # Also register package name if it's __init__.py
            if parts[-1] == "__init__.py":
                package_name = ".".join(parts[:-1])
                module_to_file[package_name] = p
            module_to_file[mod_name] = p
            
    # Regex to find imports
    import_re = re.compile(r'^\s*(?:import\s+([\w\.,\s]+)|from\s+([\w\.]+)\s+import)', re.MULTILINE)
    
    # Analyze imports in each python file
    for p in all_py:
        rel = rel_paths[p]
        # Ignore tests and scratch files when analyzing what imports what
        # (unless we want to see if tests import them)
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Error reading {rel}: {e}")
            continue
            
        for match in import_re.finditer(content):
            imp_part = match.group(1) or match.group(2)
            if imp_part:
                # Handle comma-separated imports
                parts = [x.strip() for x in re.split(r'[\s,]+', imp_part)]
                for part in parts:
                    if part:
                        file_imports[p].add(part)

    # Let's check which files are imported by other files
    # We distinguish:
    # 1. Imports from within the core pipeline (main, core, pipeline, utils, schemas)
    # 2. Imports from tests
    imported_by_code = defaultdict(list)
    imported_by_tests = defaultdict(list)
    
    for importer_file, imports in file_imports.items():
        importer_rel = rel_paths[importer_file]
        is_test = "tests" in importer_rel.parts
        is_scratch = "scratch" in importer_rel.parts
        
        for imp in imports:
            # Find if this import refers to one of our modules
            matched_file = None
            # Match exact module, or prefix
            for mod_name, mod_file in module_to_file.items():
                if imp == mod_name or imp.startswith(mod_name + "."):
                    matched_file = mod_file
                    break
            
            if matched_file:
                if is_test:
                    imported_by_tests[matched_file].append(str(importer_rel))
                elif not is_scratch:
                    imported_by_code[matched_file].append(str(importer_rel))

    print("=== POTENTIALLY UNUSED/UNIMPORTED CODE MODULES ===")
    unused_modules = []
    for p in all_py:
        rel = rel_paths[p]
        # Only care about core components: core, pipeline, utils, schemas, tools
        if not any(x in rel.parts for x in ["core", "pipeline", "utils", "schemas", "tools"]):
            continue
        if rel.name == "__init__.py":
            continue
            
        code_importers = imported_by_code[p]
        test_importers = imported_by_tests[p]
        
        # Check if imported in main.py directly
        main_imports = []
        if str(rel) in imported_by_code:
            # check if main.py is in the importers
            pass
            
        if not code_importers:
            unused_modules.append((rel, test_importers))
            
    for rel, test_imps in sorted(unused_modules):
        print(f"- {rel}")
        if test_imps:
            print(f"  (Note: Imported in tests: {', '.join(test_imps)})")
        else:
            print("  (Warning: Completely unimported in both code and tests!)")

    print("\n=== EMPTY / __init__.py ONLY DIRECTORIES ===")
    # Find folders in core/ that only contain __init__.py and/or __pycache__
    for r, d, fs in os.walk("core"):
        r_path = Path(r)
        # filter out __pycache__
        files = [f for f in fs if f != "__pycache__"]
        subdirs = [sd for sd in d if sd != "__pycache__"]
        if len(files) == 1 and files[0] == "__init__.py" and len(subdirs) == 0:
            print(f"- {r_path} (Contains only __init__.py)")
        elif len(files) == 0 and len(subdirs) == 0:
            print(f"- {r_path} (Completely empty)")

    print("\n=== STANDALONE / DIAGNOSTIC / SCRATCH SCRIPTS IN ROOT ===")
    root_files = [f for f in os.listdir(".") if os.path.isfile(f) and f.endswith(".py")]
    for rf in sorted(root_files):
        if rf in ["main.py", "dxf.py"]:
            continue
        print(f"- {rf}")

if __name__ == "__main__":
    main()
