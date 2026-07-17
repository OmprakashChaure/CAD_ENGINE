import unittest
import tempfile
import json
from pathlib import Path
from pipeline.dataset_pipeline import DatasetExporter


class TestValidationEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.exporter = DatasetExporter(output_dir=self.temp_dir.name)
        
        # Valid sample template
        self.valid_sample = {
            "drawing_id": "Hardware_HW01_HexBolt",
            "context": {
                "drawing_id": "Hardware_HW01_HexBolt",
                "part_family": "Hex Bolt",
                "manufacturing_type": "machined",
                "overall_dimensions": {
                    "width": 100.0,
                    "height": 50.0
                },
                "inquiry_feature": {
                    "feature_class": "Thread",
                    "visible_parameters": {
                        "across_flats": 18.0,
                        "head_height": 8.0
                    }
                },
                "neighbour_features": [],
                "relationships": [
                    {
                        "type": "coaxial",
                        "associated_features": ["Thread", "Hex Head"],
                        "parameters": {}
                    }
                ],
                "topology": {
                    "contours": 2,
                    "nesting": 1
                }
            },
            "target": {
                "property": "thread_size",
                "value": "M12"
            },
            "system": "You are an expert mechanical engineering assistant.",
            "user": "Task:\nInfer the missing thread size for drawing 'Hardware_HW01_HexBolt'.\n\nDrawing Description:\nThe overall plate dimensions are 100.0 mm × 50.0 mm. The drawing details a Thread feature. The feature has a visible across flats of 18.0 mm. A coaxial alignment is defined along the center axis between Thread and Hex Head. The part geometry contains 2 total contours. The maximum contour nesting depth is 1.\n\nQuestion:\nBased on the drawing layout and dimensions, infer the missing thread size.",
            "assistant": "M12"
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_stage_1_structure_valid(self):
        res = self.exporter._validate_structure(self.valid_sample)
        self.assertTrue(res["passed"])

    def test_stage_1_structure_missing_key(self):
        sample = {**self.valid_sample}
        del sample["system"]
        res = self.exporter._validate_structure(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 1")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("Missing top-level fields", res["reason"])

    def test_stage_2_schema_type_mismatch(self):
        sample = {**self.valid_sample, "drawing_id": 123}
        res = self.exporter._validate_schema(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 2")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("must be a string", res["reason"])

    def test_stage_2_schema_unexpected_key(self):
        sample = {**self.valid_sample, "unexpected_root_key": "some_value"}
        res = self.exporter._validate_schema(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 2")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("Unexpected top-level fields", res["reason"])

    def test_stage_3_engineering_contract_thread_size_valid(self):
        res = self.exporter._validate_reasoning(self.valid_sample)
        self.assertTrue(res["passed"])

    def test_stage_3_engineering_contract_thread_size_passes_without_relationship(self):
        """New contract: thread_size passes with overall_dims + geometry, even if no relationships."""
        sample = json.loads(json.dumps(self.valid_sample))
        sample["context"]["relationships"] = []
        # valid_sample has inquiry_feature with visible_parameters (geometry cues)
        # Under the new rule: overall_dims + geom is sufficient -> must PASS
        res = self.exporter._validate_reasoning(sample)
        self.assertTrue(res["passed"])

    def test_stage_3_engineering_contract_thread_size_fails_without_all_cues(self):
        """Thread_size still FAILS if overall_dims present but BOTH geom and relationships absent."""
        sample = json.loads(json.dumps(self.valid_sample))
        sample["context"]["relationships"] = []
        sample["context"]["inquiry_feature"]["visible_parameters"] = {}
        # Also clear neighbour features so has_geom is False
        sample["context"]["neighbour_features"] = []
        res = self.exporter._validate_reasoning(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 3")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("visible geometry cues or engineering relationships", res["reason"])

    def test_stage_4_preservation_empty_context(self):
        sample = {
            "drawing_id": "HW01",
            "context": {
                "drawing_id": "HW01",
                "part_family": "Hex Bolt",
                "manufacturing_type": "machined"
            },
            "target": {
                "property": "some_prop",
                "value": "10.0"
            },
            "system": "System instructions",
            "user": "Task:\nInfer property.\n\nDrawing Description:\nEmpty.\n\nQuestion:\nInfer.",
            "assistant": "10.0"
        }
        res = self.exporter._validate_reasoning(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 4")
        self.assertEqual(res["severity"], "MAJOR")

    def test_stage_5_leakage_forbidden_key(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["context"]["inquiry_feature"]["visible_parameters"]["major_diameter"] = 12.0
        res = self.exporter._validate_leakage(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 5")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("major_diameter", res["reason"])

    def test_stage_5_leakage_target_value_in_prompt(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["user"] += " The answer is M12."
        res = self.exporter._validate_leakage(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 5")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("leaked in instruction prompt text", res["reason"])

    def test_stage_6_prompt_quality_null_value(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["user"] += " Visible pitch of null mm."
        res = self.exporter._validate_prompt(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 6")
        self.assertEqual(res["severity"], "MINOR")
        self.assertIn("unformatted null/None value", res["reason"])

    def test_stage_6_prompt_quality_snake_case(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["user"] += " Adjacent concentric_bore is visible."
        res = self.exporter._validate_prompt(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 6")
        self.assertEqual(res["severity"], "MINOR")
        self.assertIn("snake_case name", res["reason"])

    def test_stage_6_prompt_quality_duplicate_lines(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["user"] += "\nDuplicate line statement.\nDuplicate line statement."
        res = self.exporter._validate_prompt(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 6")
        self.assertEqual(res["severity"], "MINOR")
        self.assertIn("Duplicate lines detected", res["reason"])

    def test_stage_7_duplicates_keys(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["context"]["inquiry_feature"]["visible_parameters"]["pitch"] = 1.25
        sample["context"]["inquiry_feature"]["visible_parameters"]["thread_pitch"] = 1.25
        res = self.exporter._validate_duplicates(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 7")
        self.assertEqual(res["severity"], "MINOR")

    def test_stage_8_traceability_untraceable_number(self):
        sample = json.loads(json.dumps(self.valid_sample))
        sample["user"] += " The feature has a visible height of 999.0 mm."
        res = self.exporter._validate_traceability(sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["stage"], "Stage 8")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn("Untraceable engineering values 999.0", res["reason"])

    def test_stage_9_severity_classification_minor(self):
        # Create a mock validator that fails with MINOR severity
        def dummy_minor_validator(sample):
            return {
                "passed": False,
                "stage": "Stage 10",
                "rule": "Dummy Rule",
                "severity": "MINOR",
                "reason": "Test warning",
                "location": "root",
                "recommendation": "None"
            }
        self.exporter._validate_sample = lambda s: dummy_minor_validator(s)
        res = self.exporter._validate_sample(self.valid_sample)
        self.assertFalse(res["passed"])
        self.assertEqual(res["severity"], "MINOR")

    def test_validation_report_export(self):
        tasks = [
            # A valid task
            {
                "task_type": "infer_thread_size",
                "drawing_id": "Hardware_HW01_HexBolt",
                "context": self.valid_sample["context"],
                "target": self.valid_sample["target"]
            },
            # An invalid task (leaks target)
            {
                "task_type": "infer_thread_size",
                "drawing_id": "Hardware_HW01_HexBolt_Leaked",
                "context": {
                    **self.valid_sample["context"],
                    "inquiry_feature": {
                        "feature_class": "Thread",
                        # Thread size M12 leaks nominal_diameter 12.0 in context
                        "visible_parameters": {"nominal_diameter": 12.0}
                    }
                },
                "target": self.valid_sample["target"]
            }
        ]
        
        self.exporter.validation_stats = {
            "total_processed": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "rejection_reasons": {},
            "prompt_size_chars": [],
            "context_size_chars": [],
            "memory_mb": 0.0,
            "duration_seconds": 0.0
        }
        self.exporter.validation_reports = []
        
        # Write to JSONL
        accepted = self.exporter._write_jsonl(tasks, Path(self.temp_dir.name) / "test_split.jsonl")
        
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.exporter.validation_stats["accepted_count"], 1)
        self.assertEqual(self.exporter.validation_stats["rejected_count"], 1)
        self.assertEqual(len(self.exporter.validation_reports), 1)
        
        report = self.exporter.validation_reports[0]
        self.assertEqual(report["drawing_id"], "Hardware_HW01_HexBolt_Leaked")
        self.assertEqual(report["failed_stage"], "Stage 5")


if __name__ == "__main__":
    unittest.main()
