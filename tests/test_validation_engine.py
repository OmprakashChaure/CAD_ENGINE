import unittest
import tempfile
import json
from pathlib import Path
from pipeline.dataset_pipeline import DatasetExporter


class TestValidationEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.exporter = DatasetExporter(output_dir=self.temp_dir.name)
        
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

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validation_passes_for_valid_record(self):
        res = self.exporter._validate_sample(self.valid_record)
        self.assertTrue(res["passed"])

    def test_validation_fails_missing_drawing_id(self):
        record = {**self.valid_record}
        del record["drawing_id"]
        res = self.exporter._validate_sample(record)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Structural")
        self.assertEqual(res["rule"], "DrawingID")

    def test_validation_fails_missing_mandatory_field(self):
        record = {**self.valid_record}
        del record["topology"]
        res = self.exporter._validate_sample(record)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Structural")
        self.assertEqual(res["rule"], "MandatoryFields")

    def test_validation_fails_incorrect_type(self):
        record = {**self.valid_record, "features": "not-a-list"}
        res = self.exporter._validate_sample(record)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Schema")
        self.assertEqual(res["rule"], "FeaturesType")

    def test_validation_fails_if_internal_id_leaks(self):
        record = json.loads(json.dumps(self.valid_record))
        # Leak internal pipeline id in features list
        record["features"][0]["candidate_id"] = "hc_123"
        res = self.exporter._validate_sample(record)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Leakage")
        self.assertEqual(res["rule"], "PipelineIDs")

    def test_validation_fails_if_internal_prefix_leaks_in_values(self):
        record = json.loads(json.dumps(self.valid_record))
        # Leak prefix in relationships list
        record["relationships"][0]["feature_ids"].append("hc_999")
        res = self.exporter._validate_sample(record)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Leakage")
        self.assertEqual(res["rule"], "PipelineIDs")


if __name__ == "__main__":
    unittest.main()
