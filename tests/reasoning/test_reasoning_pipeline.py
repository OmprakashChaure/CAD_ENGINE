import json
import tempfile
import unittest
from pathlib import Path

from pipeline.reasoning_pipeline import ReasoningPipeline


class TestReasoningPipeline(unittest.TestCase):
    def test_existing_baseline_split_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "phase7_export"
            export_dir.mkdir()
            for split in ("train", "validation", "test"):
                (export_dir / f"{split}.jsonl").write_text("")

            (export_dir / "validation.jsonl").write_text(
                json.dumps({"drawing_id": "Bearing_Housing_BH09"}) + "\n"
            )

            pipeline = ReasoningPipeline(temp_dir)
            splits = pipeline._baseline_split_map(["train", "validation", "test"])

            self.assertEqual(splits["Bearing_Housing_BH09"], "validation")


if __name__ == "__main__":
    unittest.main()
