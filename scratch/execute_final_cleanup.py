import os
import shutil
import stat
from pathlib import Path

def main():
    print("Starting Final Repository Consolidation Cleanup...")

    # 1. Define placeholder files to archive
    placeholders = {
        "core/reader/dxf_reader.py": "archive/placeholders/dxf_reader.py",
        "core/classifiers/role_classifier.py": "archive/placeholders/role_classifier.py",
        "core/features/feature_inferrer.py": "archive/placeholders/feature_inferrer.py",
        "core/semantics/semantic_enricher.py": "archive/placeholders/semantic_enricher.py",
        "core/validation/schema_validator.py": "archive/placeholders/schema_validator.py",
        "core/compression/schema_formatter.py": "archive/placeholders/schema_formatter.py",
        "core/exporters/json_exporter.py": "archive/placeholders/json_exporter.py",
        "core/grouping/bolt_detector.py": "archive/placeholders/bolt_detector.py",
        "core/grouping/spacing_detector.py": "archive/placeholders/spacing_detector.py",
        "core/grouping/relationship_builder.py": "archive/placeholders/relationship_builder.py"
    }

    archive_dir = Path("archive/placeholders")
    archive_dir.mkdir(parents=True, exist_ok=True)

    for src_str, dst_str in placeholders.items():
        src = Path(src_str)
        dst = Path(dst_str)
        if src.exists():
            print(f"Archiving placeholder: {src} -> {dst}")
            try:
                os.chmod(src, stat.S_IWRITE)
                shutil.move(src, dst)
            except Exception as e:
                print(f"Error archiving {src}: {e}")
        else:
            print(f"Source file does not exist or already archived: {src}")

    # 2. Define unused utility and empty test files to delete
    files_to_delete = [
        "utils/geometry_utils.py",
        "utils/graph_utils.py",
        "utils/visualization.py",
        "pipeline/full_pipeline.py",
        "tests/test_features.py",
        "tests/test_filters.py",
        "tests/test_pipeline.py",
        "tests/test_reader.py"
    ]

    for f_str in files_to_delete:
        f = Path(f_str)
        if f.exists():
            print(f"Deleting unused/empty file: {f}")
            try:
                os.chmod(f, stat.S_IWRITE)
                os.remove(f)
            except Exception as e:
                print(f"Error deleting {f}: {e}")
        else:
            print(f"File already removed: {f}")

    print("Final Cleanup Completed.")

if __name__ == "__main__":
    main()
