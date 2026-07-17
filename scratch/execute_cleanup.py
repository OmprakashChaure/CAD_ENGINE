import os
import shutil
import stat
import time
from pathlib import Path

def remove_readonly(func, path, excinfo):
    # Clear the read-only bit and retry the removal
    os.chmod(path, stat.S_IWRITE)
    func(path)

def safe_rmtree(path: Path):
    # Try deleting a directory tree with retries
    for attempt in range(5):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
            return True
        except Exception as e:
            if attempt == 4:
                print(f"Warning: Could not remove directory {path}: {e}")
                return False
            time.sleep(0.5)

def main():
    print("Starting Repository Consolidation Cleanup (Robust)...")

    # 1. Define files to delete
    files_to_delete = [
        "pipeline/dataset_pipeline_backup_before_llm_refactor.py",
        "gear_spline_generator.py"
    ]

    for f_path in files_to_delete:
        p = Path(f_path)
        if p.exists():
            print(f"Deleting duplicate file: {p.resolve()}")
            try:
                os.chmod(p, stat.S_IWRITE)
                os.remove(p)
            except Exception as e:
                print(f"Warning: Could not delete file {p}: {e}")
        else:
            print(f"File already removed: {p}")

    # 2. Define intermediate run directories to clean
    # Preserve 2026_06_25_18_39_43 (historical canonical run) and 2026_06_29_10_57_29 (current run)
    preserved_runs = {"2026_06_25_18_39_43", "2026_06_29_10_57_29"}

    intermediate_dir = Path("data/intermediate")
    if intermediate_dir.exists():
        for run_folder in intermediate_dir.iterdir():
            if run_folder.is_dir() and run_folder.name not in preserved_runs:
                print(f"Deleting obsolete intermediate run: {run_folder.resolve()}")
                safe_rmtree(run_folder)
            elif run_folder.name in preserved_runs:
                print(f"Preserving verified run directory: {run_folder.resolve()}")

    print("Cleanup Completed.")

if __name__ == "__main__":
    main()
