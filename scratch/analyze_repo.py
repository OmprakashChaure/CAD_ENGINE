import re
import ast
import json
import hashlib
from pathlib import Path
from collections import defaultdict

def extract_imports_and_docstring(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    docstring = ""
    try:
        tree = ast.parse(content)
        docstring = ast.get_docstring(tree) or ""
        docstring = docstring.split("\n")[0] # First line
    except Exception:
        pass

    imports = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    except Exception:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("import "):
                parts = line.split()
                if len(parts) > 1:
                    imports.append(parts[1])
            elif line.startswith("from "):
                parts = line.split()
                if len(parts) > 1:
                    imports.append(parts[1])

    local_imports = []
    for imp in imports:
        first_part = imp.split(".")[0]
        if first_part in ("core", "pipeline", "schemas", "utils", "tools", "tests"):
            local_imports.append(imp)
        elif Path(f"{first_part}.py").exists():
            local_imports.append(first_part)
            
    return docstring, sorted(list(set(local_imports))), content

def main():
    root = Path(".")
    exclude_dirs = {".git", ".kiro", ".pytest_cache", "__pycache__", ".vscode", "Cad_Engine", "data", "outputs", "pdf"}
    
    python_files = []
    for p in root.rglob("*.py"):
        if not any(x in p.parts for x in exclude_dirs):
            python_files.append(p)
            
    python_files.sort()
    
    file_info = {}
    imported_by_map = defaultdict(list)
    
    for pf in python_files:
        rel_path = pf.as_posix()
        docstring, imports, content = extract_imports_and_docstring(pf)
        
        category = "Production"
        if "scratch/" in rel_path:
            category = "Utility/Scratch"
        elif "tests/" in rel_path:
            category = "Test"
        elif "tools/" in rel_path:
            category = "Utility/Tool"
        elif "backup" in rel_path or "copy" in rel_path or "temp" in rel_path:
            category = "Backup"
        elif rel_path.endswith("_generator.py") or rel_path == "pdf_exercises_batch1_generator.py":
            category = "Utility/Generator"
        
        file_info[rel_path] = {
            "purpose": docstring or "No docstring",
            "imports": imports,
            "category": category,
            "content": content,
            "hash": hashlib.md5(content.encode("utf-8")).hexdigest()
        }

    for rel_path, info in file_info.items():
        for imp in info["imports"]:
            imp_path = imp.replace(".", "/") + ".py"
            if imp_path in file_info:
                imported_by_map[imp_path].append(rel_path)
            elif Path(imp + ".py").exists():
                imp_path_root = (imp + ".py")
                imported_by_map[imp_path_root].append(rel_path)
                
    duplicates = []
    seen_hashes = {}
    for rel_path, info in file_info.items():
        h = info["hash"]
        if h in seen_hashes:
            duplicates.append((seen_hashes[h], rel_path, 1.0))
        else:
            seen_hashes[h] = rel_path
            
    from difflib import SequenceMatcher
    for p1 in file_info:
        for p2 in file_info:
            if p1 >= p2:
                continue
            if file_info[p1]["category"] == "Utility/Generator" and file_info[p2]["category"] == "Utility/Generator":
                continue 
            if file_info[p1]["category"] == "Test" and file_info[p2]["category"] == "Test":
                continue 
            
            len1 = len(file_info[p1]["content"])
            len2 = len(file_info[p2]["content"])
            if max(len1, len2) == 0:
                continue
            if abs(len1 - len2) / max(len1, len2) > 0.3:
                continue 
                
            ratio = SequenceMatcher(None, file_info[p1]["content"], file_info[p2]["content"]).ratio()
            if ratio > 0.7:
                duplicates.append((p1, p2, ratio))
                
    output_lines = []
    output_lines.append("# REPOSITORY AUDIT\n")
    output_lines.append("| File | Category | Imported By | Imports | Purpose |\n")
    output_lines.append("| --- | --- | --- | --- | --- |\n")
    for rel_path, info in file_info.items():
        imp_by = ", ".join(imported_by_map[rel_path]) or "None"
        imps = ", ".join(info["imports"]) or "None"
        purpose = info["purpose"].replace("|", "\\|").replace("\n", " ")
        output_lines.append(f"| {rel_path} | {info['category']} | {imp_by} | {imps} | {purpose} |\n")
        
    output_lines.append("\n# DUPLICATE DETECTION\n")
    for orig, dup, ratio in duplicates:
        output_lines.append(f"\nOriginal: {orig}\nDuplicate: {dup}\nSimilarity: {ratio:.2%}\n")
        
    with open("scratch/repo_audit_output.txt", "w", encoding="utf-8") as out_f:
        out_f.writelines(output_lines)
    print("Done! Output written to scratch/repo_audit_output.txt")
        
if __name__ == "__main__":
    main()
