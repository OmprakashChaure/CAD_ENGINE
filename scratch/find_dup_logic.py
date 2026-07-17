import ast
import hashlib
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

def get_functions_and_classes(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    try:
        tree = ast.parse(content)
    except Exception:
        return [], []

    classes = []
    functions = []
    
    # Simple normalizer for comparing structure/code lines
    def clean_source(node):
        try:
            # We can use ast.unparse in Python 3.9+
            return ast.unparse(node).strip()
        except AttributeError:
            # Fallback for older python: just get the source code lines
            lines = content.splitlines()
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(lines[start:end]).strip()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            src = clean_source(node)
            classes.append({
                "name": node.name,
                "src": src,
                "line": node.lineno,
                "node": node
            })
        elif isinstance(node, ast.FunctionDef):
            # Exclude nested functions for simplicity, or keep them if they are top-level
            # Let's check if the parent is a Module (meaning it's a global function) or ClassDef
            # For simplicity, we get all functions
            src = clean_source(node)
            functions.append({
                "name": node.name,
                "src": src,
                "line": node.lineno,
                "node": node
            })
            
    return classes, functions

def main():
    root = Path(".")
    exclude_dirs = {".git", ".kiro", ".pytest_cache", "__pycache__", ".vscode", "Cad_Engine", "data", "outputs", "pdf"}
    
    python_files = []
    for p in root.rglob("*.py"):
        if not any(x in p.parts for x in exclude_dirs):
            python_files.append(p)
            
    python_files.sort()
    
    all_classes = defaultdict(list)
    all_functions = defaultdict(list)
    
    # Map from file to its classes/functions
    file_to_nodes = {}
    
    for pf in python_files:
        rel_path = pf.as_posix()
        classes, functions = get_functions_and_classes(pf)
        file_to_nodes[rel_path] = (classes, functions)
        
        for c in classes:
            all_classes[c["name"]].append((rel_path, c))
        for f in functions:
            # Skip common magic methods
            if f["name"].startswith("__") and f["name"].endswith("__"):
                continue
            all_functions[f["name"]].append((rel_path, f))

    output_lines = []
    # 1. Exact Duplicate Names
    output_lines.append("=== NAME DUPLICATES ===\n")
    output_lines.append("\n--- Duplicate Classes ---\n")
    for name, occurrences in all_classes.items():
        if len(occurrences) > 1:
            files = [occ[0] for occ in occurrences]
            output_lines.append(f"Class '{name}' found in: {', '.join(files)}\n")
            
    output_lines.append("\n--- Duplicate Functions/Methods ---\n")
    for name, occurrences in all_functions.items():
        if len(occurrences) > 1:
            files = [occ[0] for occ in occurrences]
            if len(set(files)) > 1:
                output_lines.append(f"Function '{name}' found in: {', '.join(files)}\n")

    # 2. Structural/Content Duplication (sequence matcher)
    output_lines.append("\n=== CONTENT DUPLICATION (SIMILARITY > 85%) ===\n")
    
    # Compare classes
    class_list = []
    for name, occurrences in all_classes.items():
        for file_path, c in occurrences:
            class_list.append((file_path, name, c["src"]))
            
    for i in range(len(class_list)):
        for j in range(i+1, len(class_list)):
            f1, n1, src1 = class_list[i]
            f2, n2, src2 = class_list[j]
            if f1 == f2:
                continue
            if len(src1) < 100 or len(src2) < 100:
                continue
            if abs(len(src1) - len(src2)) / max(len(src1), len(src2)) > 0.15:
                continue
                
            ratio = SequenceMatcher(None, src1, src2).ratio()
            if ratio > 0.85:
                output_lines.append(f"\nClass Match: {f1}:: {n1} <-> {f2}:: {n2}\nSimilarity: {ratio:.2%}\n")
                
    # Compare functions
    func_list = []
    for name, occurrences in all_functions.items():
        for file_path, f in occurrences:
            if len(f["src"]) < 150:
                continue
            func_list.append((file_path, name, f["src"]))
            
    for i in range(len(func_list)):
        for j in range(i+1, len(func_list)):
            f1, n1, src1 = func_list[i]
            f2, n2, src2 = func_list[j]
            if f1 == f2:
                continue
            if abs(len(src1) - len(src2)) / max(len(src1), len(src2)) > 0.15:
                continue
            ratio = SequenceMatcher(None, src1, src2).ratio()
            if ratio > 0.85:
                output_lines.append(f"\nFunction Match: {f1}:: {n1} <-> {f2}:: {n2}\nSimilarity: {ratio:.2%}\n")

    with open("scratch/dup_audit_output.txt", "w", encoding="utf-8") as out_f:
        out_f.writelines(output_lines)
    print("Done! Output written to scratch/dup_audit_output.txt")

if __name__ == "__main__":
    main()
