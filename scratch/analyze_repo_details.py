import ast
from pathlib import Path

def get_imports_and_classes_funcs(file_path: Path):
    try:
        content = file_path.read_text("utf-8")
        tree = ast.parse(content)
    except Exception as e:
        return set(), [], [], 0

    imports = set()
    classes = []
    funcs = []
    loc = len(content.splitlines())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            funcs.append(node.name)

    return imports, classes, funcs, loc

def main():
    root = Path(".")
    py_files = sorted([p for p in root.glob("**/*.py") if not any(part.startswith('.') or part == 'Cad_Engine' or part == '__pycache__' for part in p.parts)])

    # Map file paths to module names
    module_to_file = {}
    file_to_module = {}
    for p in py_files:
        parts = p.with_suffix("").parts
        mod_name = ".".join(parts)
        module_to_file[mod_name] = p
        file_to_module[p] = mod_name

    # Analyze imports for each file
    file_imports = {}
    file_imported_by = {p: set() for p in py_files}

    for p in py_files:
        imports, classes, funcs, loc = get_imports_and_classes_funcs(p)
        file_imports[p] = imports

        # Determine which other files in the repo import this one
        for imp in imports:
            # Check if this import matches any of our repo modules
            for mod_name, target_file in module_to_file.items():
                if imp == mod_name or imp.startswith(mod_name + "."):
                    file_imported_by[target_file].add(p)

    # Print results to UTF-8 file
    with open("scratch/detailed_repo_analysis.txt", "w", encoding="utf-8") as f:
        f.write("ANALYSIS RESULTS:\n")
        for p in py_files:
            f.write("---\n")
            f.write(f"File: {p.as_posix()}\n")
            f.write(f"Module: {file_to_module[p]}\n")
            f.write(f"Imports: {list(file_imports[p])}\n")
            f.write(f"Imported By: {[ib.as_posix() for ib in file_imported_by[p]]}\n")
            _, classes, funcs, loc = get_imports_and_classes_funcs(p)
            f.write(f"Classes: {classes}\n")
            f.write(f"Functions: {funcs}\n")
            f.write(f"LOC: {loc}\n")

if __name__ == "__main__":
    main()
