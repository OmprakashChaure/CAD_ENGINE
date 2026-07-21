import json
import tempfile
import unittest
from pathlib import Path

from pipeline.dataset_pipeline import DatasetExporter


class TestDatasetExporterPretty(unittest.TestCase):
    def setUp(self):
        # Valid engineering record template
        self.valid_record = {
            "drawing_id": "Hardware_HW01_HexBolt",
            "part_family": "Hardware",
            "manufacturing_type": "turned",
            "overall_dimensions": {
                "width": 100.0,
                "height": 50.0
            },
            "topology": {
                "contours": 2,
                "nesting": 1,
                "holes": 1,
                "regions": 1
            },
            "features": [
                {
                    "feature_id": "thread_1",
                    "feature_class": "thread",
                    "parameters": {"nominal_diameter": 12.0}
                }
            ],
            "relationships": [
                {
                    "relationship_id": "coaxial_1",
                    "relationship_type": "coaxial",
                    "feature_ids": ["thread_1", "hex_head_1"],
                    "parameters": {}
                }
            ],
            "annotations": [
                {
                    "handle": "A1",
                    "text": "MATERIAL: STEEL",
                    "position": [0.0, 0.0]
                }
            ],
            "dimension_entities": [
                {
                    "handle": "D1",
                    "text": "100.0",
                    "value": 100.0,
                    "dimension_type": "horizontal"
                }
            ],
            "engineering_constraints": [
                {
                    "type": "material",
                    "value": "STEEL"
                }
            ],
            "metadata": {
                "feature_count": 1,
                "relationship_count": 1,
                "has_hierarchy": False
            }
        }

    def test_exporter_writes_both_jsonl_and_pretty_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)
            exporter = DatasetExporter(output_path)
            
            # Initialize required validation attributes on exporter
            exporter.validation_reports = []
            exporter.validation_stats = {
                "total_processed": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "rejection_reasons": {}
            }
            
            # Run _write_jsonl
            path = output_path / "train.jsonl"
            accepted = exporter._write_jsonl([self.valid_record], path)
            
            self.assertEqual(len(accepted), 1)
            
            # Check standard jsonl exists
            self.assertTrue(path.exists())
            with open(path, "r") as f:
                jsonl_lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(jsonl_lines), 1)
            self.assertEqual(jsonl_lines[0]["drawing_id"], "Hardware_HW01_HexBolt")
            
            # Check pretty-printed json exists
            pretty_path = output_path / "train_pretty.json"
            self.assertTrue(pretty_path.exists())
            with open(pretty_path, "r") as f:
                pretty_data = json.load(f)
            self.assertEqual(len(pretty_data), 1)
            self.assertEqual(pretty_data[0]["drawing_id"], "Hardware_HW01_HexBolt")
            
            # Check they are identical
            self.assertEqual(jsonl_lines[0], pretty_data[0])
            
            # Check pretty printing indentation is 4 spaces
            pretty_content = pretty_path.read_text()
            self.assertIn("    ", pretty_content)

    def test_exporter_writes_empty_pretty_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)
            exporter = DatasetExporter(output_path)
            
            # Run _write_empty
            exporter._write_empty()
            
            for split in ["train", "validation", "test"]:
                jsonl_path = output_path / f"{split}.jsonl"
                pretty_path = output_path / f"{split}_pretty.json"
                
                self.assertTrue(jsonl_path.exists())
                self.assertEqual(jsonl_path.stat().st_size, 0)
                
                self.assertTrue(pretty_path.exists())
                with open(pretty_path, "r") as f:
                    data = json.load(f)
                self.assertEqual(data, [])


if __name__ == "__main__":
    unittest.main()
